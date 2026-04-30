# 사내 AD / LDAP 인증 연동 가이드

LF 사내 Active Directory 서버 정보, LDAP bind 검증 결과, 그리고 PWA(모바일) 자체 로그인 시 LDAP 연동 설계를 정리한 문서.

---

## 1. AD 서버 기본 정보

| 항목 | 값 |
|------|-----|
| AD DNS 도메인 | `ad.landf` |
| NetBIOS 도메인 | `ADLANDF` |
| 도메인 컨트롤러 호스트명 | `LANDFAD-HA.ad.landf` |
| DC IP 주소 | `192.168.100.98` |
| Base DN | `DC=ad,DC=landf` |
| 회사 메일 도메인 | `landf.co.kr` (AD `mail` 속성 기준) |

### OU 구조 (예시)

AD 사용자는 부서별 OU 트리에 배치되어 있음:

```
DC=ad,DC=landf
└─ OU=LANDFUsers
   └─ OU=정보보안부문
      └─ OU=IT센터
         └─ OU=IT운영팀
            └─ CN=A2304013   (사번이 CN)
```

---

## 2. 인증 속성 매핑 (CRITICAL)

| AD 속성 | 예시 값 | 의미 |
|---------|---------|------|
| `sAMAccountName` | `wg0403` | **AD 로그인 계정명** (사용자가 매일 PC 로그인 시 입력) |
| `userPrincipalName` (UPN) | `wg0403@ad.landf` | 이메일 형태 로그인 이름 (UPN bind에 사용) |
| `cn` | `A2304013` | **사번** (Common Name에 저장) |
| `displayName` | `A2304013` | 사번 (표시명) |
| `mail` | `wg0403@landf.co.kr` | 회사 이메일 |
| `employeeID` / `employeeNumber` | (없음) | **사용 불가** — AD에 해당 속성 미설정 |

### ⚠️ 핵심 주의사항

- **로그인 계정명 ≠ 사번**: `wg0403`(계정) vs `A2304013`(사번)
- AD에 `employeeID`/`employeeNumber` 속성이 없음 → 사번을 알려면 `cn`을 읽거나, 외부 매핑(`v_user_info_mapping`)을 사용해야 함
- 우리 시스템은 PostgreSQL VIEW [`v_user_info_mapping`](backend/app/api/routes/auth.py)으로 `login_id → employee_number` 매핑을 이미 보유 (`login_id == sAMAccountName`)

---

## 3. LDAP Bind 검증 결과 (2026-04-30 wg0403 계정)

| 시도 조합 | 결과 | 비고 |
|-----------|------|------|
| LDAPS (636) + UPN | ❌ `WinError 10054` (TLS 핸드셰이크 단계에서 끊김) | 모든 bind 포맷에서 실패 |
| LDAP + StartTLS (389) | ❌ `startTLS failed - unavailable` | AD가 StartTLS 확장 미지원 |
| **LDAP plain (389) + UPN** | ✅ **성공** | `wg0403@ad.landf` + 비밀번호 |
| LDAP plain (389) + NetBIOS | (확인 안 함, UPN에서 성공) | `ADLANDF\wg0403` 형태 |
| LDAP plain (389) + sAMAccountName 단독 | (확인 안 함, UPN에서 성공) | `wg0403` 단독 |

### 운영 진입 전 필수 조치

**현재 LDAPS와 StartTLS 모두 미동작** → 평문 bind는 비밀번호가 네트워크에 노출되어 운영에 적용 불가.

다음 중 하나 필요:
1. **인프라팀 — AD 도메인 컨트롤러에 LDAPS 인증서 설치/활성화** (정석)
2. 보안기술팀 — TLS cipher 정책/StartTLS 활성화 검토
3. (선택) 검색용 서비스 계정 발급 — 사용자 검색/대량 조회 용도

→ 운영 적용 전 위 조치 완료 후 LDAPS(636)로 재검증 필수.

---

## 4. PWA 자체 로그인 설계

### 흐름

```
┌──────────────────────────────────────────────────────────┐
│ 1. PWA 로그인 화면                                          │
│    - 입력란: "AD 계정 (예: wg0403)" + "비밀번호"            │
└──────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│ 2. POST /api/v1/auth/login-ad                              │
│    body: { login_id: "wg0403", password: "..." }            │
└──────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│ 3. Backend: ldap3 bind                                       │
│    Connection(server,                                          │
│       user=f"{login_id}@ad.landf",                              │
│       password=password).bind()                                  │
│    → 성공 = 비밀번호 일치, 실패 = 인증 거부                         │
└──────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│ 4. PostgreSQL VIEW v_user_info_mapping 조회                  │
│    SELECT employee_number FROM v_user_info_mapping             │
│     WHERE login_id = $1;                                         │
│    → empno = "A2304013"                                          │
└──────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│ 5. JWT 발급 (페이로드에 empno 포함) → HttpOnly 쿠키            │
└──────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────┐
│ 6. 이후 모든 워커는 사번(empno) 기반 동작                        │
│    (메일·결재·IT/회계 VOC·LFON 계정 관리 등 모두 변경 없음)        │
└──────────────────────────────────────────────────────────┘
```

### 비밀번호 처리 정책

- **PWA·백엔드는 비밀번호를 저장하지 않음** — AD가 검증하고 우리는 결과만 받음
- 사용자가 비밀번호 변경 시에도 AD에서 변경하면 즉시 반영 (별도 동기화 불필요)
- AD 서버 장애 시 인증 자체가 불가 (의도적 설계 — 폴백 없음. 그룹웨어 SSO도 같이 죽으므로 데스크톱도 못 쓰는 상황이라 수용 가능)

### 기존 인프라 재활용

[backend/app/api/routes/auth.py](backend/app/api/routes/auth.py)에 이미 다음이 구현되어 있음:
- `users` 테이블 (`empno`, `login_id`, `name`, `password_hash`, `is_active`)
- `_get_user_by_login_id()` 함수
- JWT 발급 흐름

→ AD 연동은 `password_hash` 검증 단계만 LDAP bind로 대체하면 됨. 신규 테이블 추가 불필요.

---

## 5. 테스트 스크립트

검증용 스크립트가 [c:/tmp/ad_test.py](c:/tmp/ad_test.py)에 있음 (필요 시 재실행):

```bash
python c:/tmp/ad_test.py
```

- 사번/비밀번호 입력 (비밀번호는 입력 시 화면에 안 보임)
- LDAPS(636) → StartTLS(389) → plain LDAP(389) 순으로 자동 fallback
- UPN/NetBIOS/sAMAccountName 3가지 bind 포맷 자동 시도
- 성공 시 본인 계정 속성 출력

---

## 6. 보안 체크리스트

운영 전환 시 확인할 항목:

- [ ] AD에 LDAPS(636) 활성화 + 정상 인증서 설치 (인프라팀)
- [ ] Python `ldap3` 클라이언트가 LDAPS로 정상 bind 가능 확인
- [ ] 평문 LDAP(389) bind 코드는 **개발 환경에서만 동작**하도록 환경변수 분기
- [ ] AD 서비스 계정 발급 (검색 전용, 최소 권한)
- [ ] 비밀번호는 절대 로그/DB에 기록하지 않음 — bind 직후 메모리에서 폐기
- [ ] 실패 누적 시 계정 잠김 정책 확인 (AD 설정 따름, 우리 측 별도 처리 불필요)
- [ ] PWA 로그인 화면에 "사내망/VPN 접속 필수" 안내 명시

---

## 7. 관련 파일·문서

- [backend/app/api/routes/auth.py](../backend/app/api/routes/auth.py) — 자체 로그인 + setup_token 흐름
- [docs/jsp_sso_gosso_patch.md](jsp_sso_gosso_patch.md) — 데스크톱 SSO 인증 흐름
- [memory/lf_ad_ldap.md](../../.claude/projects/c--Users-Administrator-Documents-LFChatbot-NextJS-FastAPI/memory/lf_ad_ldap.md) — AD 정보 메모리
