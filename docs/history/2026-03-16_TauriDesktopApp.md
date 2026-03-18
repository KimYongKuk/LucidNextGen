# 2026-03-16 Tauri 데스크톱 앱 (퀵 채팅)

## 개요
기존 웹 챗봇을 OS 레벨 데스크톱 앱으로 제공하기 위해 Tauri v2 기반 데스크톱 클라이언트를 신규 구축. 시스템 트레이 상주 + 글로벌 단축키(`Ctrl+Space`) 퀵 채팅 팝업이 핵심 기능.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `desktop/` (전체) | 추가 | Tauri v2 프로젝트 신규 생성 |
| `desktop/src-tauri/src/lib.rs` | 추가 | Rust 코어: 글로벌 단축키, 시스템 트레이, 창 관리 |
| `desktop/src-tauri/src/main.rs` | 추가 | 앱 진입점 |
| `desktop/src-tauri/tauri.conf.json` | 추가 | 창 2개(main/quick), 트레이, 번들 설정 |
| `desktop/src-tauri/Cargo.toml` | 추가 | Rust 의존성 (tauri, tauri-plugin-global-shortcut) |
| `desktop/src/views/QuickChat.tsx` | 추가 | 퀵 채팅 UI (SSE 스트리밍, 마크다운, FOLLOW_UP 버튼) |
| `desktop/src/views/FullChat.tsx` | 추가 | 풀 채팅 (기존 웹 iframe 래핑) |
| `desktop/src/components/ChatMessage.tsx` | 추가 | 메시지 컴포넌트 (react-markdown + remark-gfm) |
| `desktop/index.html` | 추가 | 다크 테마 마크다운 스타일 (테이블, 코드블록 등) |
| `desktop/package.json` | 추가 | React, Tauri API, react-markdown, remark-gfm |

## 상세 내용

### 아키텍처
```
Tauri App (Windows, ~10MB)
├── Rust Core
│   ├── 글로벌 단축키: Ctrl+Space → 퀵 채팅 토글
│   ├── 시스템 트레이: 열기 / 퀵 채팅 / 종료
│   └── 창 관리: main(1200x800), quick(680x480, alwaysOnTop)
├── WebView (React + Vite)
│   ├── QuickChat: 독립 채팅 UI (직접 FastAPI 호출)
│   └── FullChat: 기존 Next.js 웹 iframe
└── 백엔드: 기존 FastAPI 서버 그대로 사용 (변경 없음)
```

### 창 구성
| 창 | 크기 | 특성 | 용도 |
|----|------|------|------|
| `main` | 1200x800 | 숨김 시작, 리사이즈 가능 | 풀 채팅 (트레이 더블클릭) |
| `quick` | 680x480 | alwaysOnTop, transparent, skipTaskbar | 퀵 채팅 팝업 |

### 퀵 채팅 기능
- SSE 스트리밍 (`/api/v1/chat/message/stream`) 직접 호출
- `react-markdown` + `remark-gfm`: 볼드, 테이블, 코드블록, 리스트 렌더링
- `<!--FOLLOW_UP:[...]-->` 파싱 → 클릭 가능한 pill 버튼 (자동 질문 전송)
- React state immutable 업데이트 (스트리밍 중복 방지)
- `Esc` 키 → 창 숨기기, 포커스 시 자동 입력 포커싱

### Rust 코어 기능
- `tauri_plugin_global_shortcut`: `Ctrl+Space` 전역 등록
- `TrayIconBuilder`: 시스템 트레이 메뉴 (열기/퀵 채팅/종료)
- 더블클릭 이벤트 → 풀 채팅 창 표시
- 비대화형 세션(SSH 등) graceful 에러 처리

### 주요 의존성
- **Rust**: tauri 2.x, tauri-plugin-global-shortcut
- **Frontend**: react 19, @tauri-apps/api, react-markdown, remark-gfm, vite

## 결정 사항 및 주의점
- **백엔드 변경 없음**: 기존 FastAPI 서버 API를 그대로 호출하여 분리 유지
- **SSO 미적용**: 퀵 채팅은 `user_id: "desktop_test"` 하드코딩 상태 (테스트용)
- **풀 채팅 SSO 이슈**: iframe으로 localhost:3000 로드 시 SSO 리다이렉트 발생 → 향후 해결 필요
- **PWA 대비 장점**: 글로벌 단축키, 시스템 트레이, alwaysOnTop 등 OS 레벨 기능 사용 가능
- **향후 확장**: 드래그앤드롭 파일 전송, 클립보드 연동, Push 알림, 로컬 파일 인덱싱
