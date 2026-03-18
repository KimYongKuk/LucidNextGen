# 2026-03-18 Blue-Green 배포 시스템 구축

## 개요
운영 서버에서 직접 코드 수정 → reload 방식의 위험한 운영을 개선하기 위해, nginx + PM2 + NSSM 기반 Blue-Green 무중단 배포 시스템을 구축했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/main.py` | 수정 | PORT 환경변수 지원 추가 |
| `frontend/lib/api/config.ts` | 수정 | nginx same-origin 프록시 지원 |
| `frontend/app/layout.tsx` | 수정 | NoticeToastProvider Suspense boundary 추가 (빌드 에러 수정) |
| `frontend/app/not-found.tsx` | 추가 | 커스텀 404 페이지 (Next.js 16 빌드 에러 수정) |
| `frontend/components/dashboard/token-usage.tsx` | 수정 | Tooltip formatter 타입 에러 수정 |
| `frontend/package.json` | 수정 | dev 포트 3099로 변경 |
| `bat/start_backend.bat` | 수정 | 개발 백엔드 포트 8099 설정 |

## 상세 내용

### 아키텍처
```
사용자 → nginx (:80, :3000)
              ├── /api/v1/*  → backend (NSSM, :8001 or :8002)
              ├── /api/auth/* → backend
              ├── /health    → backend
              └── /*         → frontend (PM2, :3001 or :3002)

개발자 → nginx (:9090)
              ├── /api/v1/*  → backend-dev (:8099)
              └── /*         → frontend-dev (:3099)
```

### 디렉토리 구조
```
C:\Services\
├── nginx\                          # 리버스 프록시
├── LFChatbot_prod\
│   ├── blue\                       # 운영 슬롯 A (:3001/:8001)
│   ├── green\                      # 운영 슬롯 B (:3002/:8002)
│   ├── deploy\
│   │   ├── deploy.bat              # 배포 스크립트
│   │   ├── rollback.bat            # 롤백 스크립트 (15초 이내)
│   │   ├── auto-deploy.bat         # 스케줄 배포 (main 변경 감지)
│   │   └── state.txt               # 현재 활성 슬롯
│   └── ecosystem.config.js         # PM2 앱 정의
├── LFChatbot_data\                 # 공유 데이터 (Junction)
└── logs\                           # 배포/서비스 로그
```

### 프로세스 관리
| 구분 | 도구 | 서비스명 |
|------|------|----------|
| Backend | NSSM (Windows Service) | LFChatbot-backend-blue/green |
| Frontend | PM2 | frontend-blue/green |
| nginx | NSSM | LFChatbot-nginx |
| PM2 복원 | NSSM | LFChatbot-pm2 |

### 자동 배포
- Task Scheduler: 매일 12:10, 22:30 실행
- main 브랜치에 새 커밋 있을 때만 배포
- 무중단: IDLE 슬롯 준비 → health check → nginx 전환 → OLD 슬롯 정지

### 브랜치 전략
- `develop`: 일상 개발, 커밋 누적
- `main`: 운영 배포 소스, develop에서 머지

## 결정 사항 및 주의점
- Docker 미사용: Windows + ChromaDB + MCP subprocess 환경에서 네이티브가 실용적
- 공유 데이터: Junction(NTFS)으로 blue/green 양쪽에서 동일 데이터 접근
- `.env.local`은 슬롯별 다름: blue는 `:8001`, dev는 `:8099` — deploy.bat에서 덮어쓰지 않도록 주의
- nginx `/api/` 라우팅: `/api/v1/*`만 백엔드, 나머지 `/api/*`는 Next.js API route
