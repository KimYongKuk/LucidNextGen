# 2026-03-19 Embed 페이지 (L&F Wiki 임베딩용)

## 개요
L&F Wiki에 iframe으로 임베딩할 수 있는 경량 채팅 페이지(`/embed`)를 추가했다. 사이드바/헤더/모달 없이 채팅만 노출하며, `chat_mode=outline_embed`로 인텐트를 OUTLINE+DIRECT로 제한한다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `frontend/app/embed/layout.tsx` | 신규 | embed 전용 레이아웃 (DataStreamProvider만) |
| `frontend/app/embed/page.tsx` | 신규 | embed 페이지 (세션 자동 생성) |
| `frontend/components/embed-chat.tsx` | 신규 | 경량 Chat 컴포넌트 (헤더/사이드바/뷰어 없음) |
| `frontend/hooks/use-simple-chat.ts` | 수정 | `chatMode` 옵션 추가 (기본값 'normal') |
| `frontend/middleware.ts` | 수정 | embed 경로 인증 실패 시 401 반환 (리다이렉트 대신) |
| `backend/app/agents/orchestrator.py` | 수정 | outline_embed 모드 인텐트 필터링 |

## 상세 내용

### 프론트엔드 구조
```
/embed 접속
  └── EmbedLayout (DataStreamProvider만, 사이드바 X)
      └── EmbedPage (세션 자동 생성)
          └── EmbedChat (경량 Chat)
              ├── 미니 헤더 ("Lucid AI" 텍스트만)
              ├── Messages (기존 재사용)
              ├── FollowUpSuggestions (기존 재사용)
              └── MultimodalInput (기존 재사용)
```

### 제거된 컴포넌트
- AppSidebar, SidebarProvider
- ChatHeader (워크스페이스 정보, 모델 선택)
- Artifact, XlsxViewerPanel, DocumentViewerPanel
- OnboardingProvider
- 워크스페이스 관련 로직

### chat_mode=outline_embed
- 프론트엔드: `useSimpleChat({ chatMode: 'outline_embed' })`
- 백엔드: orchestrator에서 인텐트 필터링
  - 허용: `Intent.OUTLINE`, `Intent.DIRECT`
  - 그 외 인텐트 → `Intent.OUTLINE`로 강제 전환

### 인증
- 기존 SSO 쿠키(`empno`) 인증 그대로 사용
- 같은 도메인이면 쿠키 자동 공유
- 다른 도메인이면 `?empno=xxx` URL 파라미터 인증
- embed 경로에서 인증 실패 시 `/unauthorized` 리다이렉트 대신 401 응답 (iframe 깨짐 방지)

## 결정 사항 및 주의점
- L&F Wiki에서 `empCode` 사번을 별도 저장하고 있음 → 같은 인증 체계
- 위키 접속 자체가 인증된 상태이므로, 추후 인증 없이 접근 가능하도록 변경 검토 가능
- iframe 삽입 시 CSP 헤더 확인 필요 (Outline 측)
- 향후 floating widget JS는 Wiki 에이전트 측에서 구현
