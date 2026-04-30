# 2026-04-30 PWA 모바일 UI + AD/LDAP 자체 로그인

## 개요

모바일 PWA 도입을 위한 1차 작업. (1) 기존 Next.js 프론트의 모바일 UX 다듬기 + PWA manifest 추가, (2) 데스크톱·모바일 통합 설치 안내 배너, (3) AD/LDAP bind를 통한 PWA용 자체 로그인(`/auth/login-ad`) 백엔드 구축. 운영 LDAPS는 인프라팀 활성화 대기 — 환경변수 한 줄(`AD_USE_LDAPS=true`)로 평문 LDAP↔LDAPS 전환되도록 설계.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `frontend/public/manifest.json` | 추가 | PWA manifest (display: standalone, icons, theme_color) |
| `frontend/app/layout.tsx` | 수정 | manifest 링크 + iOS PWA 메타(`appleWebApp`) + viewport(`viewportFit: cover`, `userScalable: false`) + themeColor |
| `frontend/middleware.ts` | 수정 | matcher에 `manifest.json` 화이트리스트 (인증 우회) |
| `frontend/tailwind.config.ts` | 수정 | shadcn `sidebar.*` 컬러 매핑 추가 — 모바일 시트 드로어가 라이트 테마에서 투명하던 버그 수정 |
| `frontend/components/install-prompt-banner.tsx` | 추가 | 데스크톱·모바일 통합 설치 안내. `beforeinstallprompt` 캐치 + iOS Safari/데스크톱 Chromium fallback 카드 |
| `frontend/app/(chat)/layout.tsx` | 수정 | `<InstallPromptBanner />` mount |
| `frontend/components/workspace-settings-modal.tsx` | 수정 | DialogContent 모바일 풀스크린(`w-screen h-[100dvh]`), 사이드바 탭 모바일에선 가로 탭바로 전환, 패딩 모바일 축소 |
| `frontend/components/workspace-agents-tab.tsx` | 수정 | 헤더 모바일에서 세로 정렬, 버튼 라벨 짧게(Store/추가), CapabilityStrip flex-wrap |
| `backend/requirements.txt` | 수정 | `ldap3==2.9.1` 추가 |
| `backend/app/services/ad_service.py` | 추가 | LDAP bind + TIMS `v_user_info_mapping` 사번 조회 통합 서비스 |
| `backend/app/api/routes/auth.py` | 수정 | `/auth/login-ad` 엔드포인트 추가 (LoginRequest 재사용, JWT 발급 흐름 동일) |
| `backend/.env` | 수정 | `AD_HOST`, `AD_DOMAIN`, `AD_USE_LDAPS=false`, `AD_PORT=389`, `AD_BIND_TIMEOUT=5` 추가 |
| `frontend/app/api/auth/login-ad/route.ts` | 추가 | Next.js 프록시 라우트 (백엔드 호출 + 쿠키 4종 설정) |
| `frontend/app/login/page.tsx` | 수정 | `NEXT_PUBLIC_AUTH_METHOD=ad` 시 `/api/auth/login-ad` 호출 + 입력 라벨/플레이스홀더 분기 |
| `frontend/.env.local` | 수정 | `NEXT_PUBLIC_AUTH_METHOD=ad` 추가 (dev 검증용) |

## 상세 내용

### 1. PWA manifest + 모바일 메타

- `manifest.json`: `name=Lucid AI`, `display=standalone`, `start_url=/`, `theme_color=#fff`, `lang=ko-KR`, icons=`/logo.png` (200×200, `purpose: any+maskable`)
- `app/layout.tsx`의 `metadata`: `manifest: "/manifest.json"` + `appleWebApp: { capable: true, statusBarStyle: "default" }`
- `viewport` export: `viewportFit: "cover"` (iPhone notch 영역 활용), `userScalable: false`, light/dark theme별 `themeColor` 분기
- `middleware.ts` matcher에 `manifest\\.json` 추가 — 미들웨어 인증이 정적 자원도 가로채 `/login` 리다이렉트하던 문제 해결

### 2. shadcn Sidebar 색상 매핑 (라이트 테마 드로어 투명 버그 수정)

- `globals.css`에 `--sidebar-background`, `--sidebar-foreground` 등 8개 CSS 변수 정의돼 있었으나 `tailwind.config.ts`에 매핑이 없어 `bg-sidebar`, `text-sidebar-foreground` 클래스가 무효였음
- 결과: 데스크톱은 `SidebarInset`의 `bg-background`로 가려져 안 보였지만 **모바일 Sheet 드로어에서 노출** — 라이트 테마 흰 배경에 검은 글자가 뒤 채팅과 겹쳐 가독성 ↓
- 수정: shadcn 표준 매핑(`sidebar.DEFAULT`, `sidebar.foreground`, `sidebar.primary-foreground` 등) 추가

### 3. InstallPromptBanner — 통합 설치 안내

- **트리거**: `beforeinstallprompt` 이벤트 (Chrome/Edge HTTPS) 또는 3초 후 fallback (iOS Safari / 데스크톱 Chromium)
- **3가지 상태**:
  - `installEvent` 보유 → 즉시 "설치" 버튼 (네이티브 설치 다이얼로그)
  - iOS Safari fallback → "방법" 버튼 → 1-2-3 단계 안내 (공유 → 홈 화면 추가)
  - 데스크톱 Chromium fallback → "방법" → 브라우저별 메뉴 경로 (Edge: `메뉴 → 기타 도구 → 앱 → 설치`, Chrome: `메뉴 → 캐스트, 저장 및 공유 → 페이지를 앱으로 설치`)
- **dismiss 정책**: `sessionStorage` — 탭 닫고 다시 열면 다시 노출
- **자동 숨김**: standalone 모드 감지 또는 `appinstalled` 이벤트 수신 시
- **레이아웃**: 모바일 풀폭 하단 / 데스크톱 우하단 토스트 (`sm:right-4 sm:max-w-md`)

### 4. AD/LDAP 자체 로그인

#### 흐름
```
PWA 로그인 폼 (login_id="wg0403" + password)
  ↓
POST /api/auth/login-ad (Next.js 프록시)
  ↓
POST :8099/api/auth/login-ad (FastAPI)
  ↓
ad_service.authenticate(login_id, password):
  1. LDAP bind (UPN 포맷: f"{login_id}@ad.landf")
     - AD_USE_LDAPS=false → 평문 LDAP(389)
     - AD_USE_LDAPS=true  → LDAPS(636) + cert validate=NONE + TLS 1.2
  2. bind 성공 시 TIMS v_user_info_mapping에서 사번 조회
     - login_id == sAMAccountName 가정
  3. 둘 다 OK → AdUser(empno, login_id, name) 반환
  ↓
JWT 발급 (_create_token, 24h)
  ↓
쿠키 4종 set: empno, login_id, user_name, auth_token(httpOnly)
```

#### ad_service.py 핵심
- `verify_ad_credentials(login_id, password)`: LDAP bind만 수행, 성공/실패 boolean
- `resolve_user_from_login_id(login_id)`: TIMS PostgreSQL 비동기 조회
- `authenticate(...)`: 위 둘을 묶음. **AD bind OK + TIMS 매핑 없음** 케이스도 401 처리(보안)
- 실패 사유는 로그에만 기록, 사용자에게는 동일 메시지 ("아이디 또는 비밀번호가 올바르지 않습니다")

#### 환경변수 분기
- `AD_USE_LDAPS` (기본 false): 운영 진입 전 true로 변경하면 LDAPS(636) + TLS 강제
- `AD_PORT`는 `AD_USE_LDAPS`에 따라 자동 디폴트 (636/389)
- `AD_BIND_TIMEOUT=5초` — AD 응답 지연 시 빠르게 실패

#### 프론트 분기
- `NEXT_PUBLIC_AUTH_METHOD=ad` 환경변수가 있으면 새 엔드포인트 + 입력 라벨 변경
- 미설정/`local` → 기존 bcrypt 동작 그대로 (프로토타입 사용자 보존)
- 빌드타임 변수이므로 운영 배포 시 빌드 옵션에 명시 필요

## 결정 사항 및 주의점

### 보안

- **비밀번호는 어디에도 저장 X** — AD가 검증, 우리는 결과만. JWT 페이로드에도 password 없음.
- **운영 적용 전 LDAPS 필수** — 평문 LDAP은 비밀번호가 네트워크 평문 전송. 사내망이라도 사고 시 책임 무거움. 인프라팀 LDAPS 활성화 + 인증서 설치 후 `AD_USE_LDAPS=true` 전환.
- **AD bind OK + TIMS 매핑 없음**도 401 처리 — 퇴사자/시스템 계정 우회 차단.
- **invalidCredentials과 LDAP 통신 실패를 사용자에겐 동일 메시지**로 응답 — 계정 유효성 정찰 차단.

### 사번 매핑

- AD `cn=A2304013` ≠ AD `sAMAccountName=wg0403`. 사번은 AD에 없으므로 무조건 TIMS `v_user_info_mapping`을 조회.
- TIMS DB 장애 시 AD 인증은 통과해도 로그인 자체가 막힘. 의도적 (사번 없으면 어떤 워커도 동작 못 함).

### 인증 방식 선택

- **환경변수 분기로 마이그레이션 점진 가능** — 일부 사용자/환경에만 AD 적용 가능.
- **두 엔드포인트 병존** (`/auth/login` + `/auth/login-ad`) — 기존 프로토타입 사용자(bcrypt) 영향 0.
- 운영 배포 시 `NEXT_PUBLIC_AUTH_METHOD=ad`로 빌드 → 모든 사용자가 AD 사용. 기존 사용자는 같은 ID/비밀번호(그룹웨어와 동일)로 로그인.

### Dev 검증 한계

- LDAPS 미동작이라 dev에서는 평문 LDAP(389)만 검증 가능.
- backend dev가 `--reload` 모드 아닌 경우 코드 변경 후 수동 재시작 필요 (확인됨).
- frontend `NEXT_PUBLIC_*`는 빌드타임 변수이지만 dev hot reload는 자동 반영.

### 알려진 외부 의존

- **인프라/보안기술팀**: 운영 AD에 LDAPS 인증서 설치 + 활성화 (현재 SSL 핸드셰이크 거부, StartTLS unavailable)
- **DBA**: TIMS `v_user_info_mapping` VIEW 유지 보수 (이미 메일/결재 워커 등에서 사용 중)

## 관련 메모리

- [memory/lf_ad_ldap.md](../../.claude/projects/c--Users-Administrator-Documents-LFChatbot-NextJS-FastAPI/memory/lf_ad_ldap.md) — AD 서버 정보 + LDAP bind 검증 결과
- [docs/AD_LDAP_Integration.md](../AD_LDAP_Integration.md) — 종합 가이드 (속성 매핑·인증 흐름·보안 체크리스트)
