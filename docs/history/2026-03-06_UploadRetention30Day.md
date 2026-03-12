# 2026-03-06 업로드 파일 7일 보관 및 자동 정리 시스템

## 개요
사용자가 대화를 위해 업로드한 파일의 원본을 디스크에 7일간 보관하고, ChromaDB 임베딩도 7일간 유지하도록 변경. 기존의 불안정한 프론트엔드 즉시삭제(sendBeacon) 방식을 제거하고, 백엔드 스케줄러 기반 자동 정리로 전환.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/api/routes/upload.py` | 수정 | 모든 업로드 파일 원본을 `data/user_uploads/{session_id}/`에 저장 |
| `backend/app/utils/chromadb_cleanup.py` | 수정 | SESSION_RETENTION_HOURS 24→720, 고아 디렉토리 정리 추가 |
| `backend/app/utils/file_cleanup.py` | 수정 | `user_uploads` 정리 대상 추가, per-target retention 지원 |
| `frontend/hooks/use-session-cleanup.ts` | 수정 | cleanup 로직 제거 (no-op), 백엔드 스케줄러에 위임 |
| `frontend/components/multimodal-input.tsx` | 수정 | `deleteSessionFiles()` 함수 및 호출 제거 |

## 상세 내용

### Before (기존)
- 업로드 파일은 ChromaDB에만 임베딩 저장, 원본은 버림 (XLSX 제외)
- 프론트엔드에서 세션 전환/브라우저 닫기 시 `sendBeacon`으로 즉시 ChromaDB 컬렉션 삭제
- `sendBeacon` 실패 시 고아 컬렉션 누적
- ChromaDB 스케줄러 기본 보관 24시간

### After (변경)
- 모든 업로드 파일 원본을 `data/user_uploads/{session_id}/`에 디스크 저장 (7일 보관)
- 프론트엔드 즉시삭제 완전 제거 → 세션 나갔다 돌아와도 파일 맥락 유지
- ChromaDB 세션 컬렉션 7일 보관 (스케줄러가 자동 정리)
- `file_cleanup.py`에 per-target retention 추가: 출력 파일(PDF/PPT 등)은 1년, 업로드 파일은 7일

### 환경변수
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SESSION_RETENTION_HOURS` | `168` | ChromaDB 세션 컬렉션 보관 (7일) |
| `UPLOAD_RETENTION_HOURS` | `168` | 업로드 원본 파일 디스크 보관 (7일) |

### 디렉토리 구조
```
backend/data/
├── user_uploads/          ← NEW: 모든 업로드 원본 보관 (7일)
│   └── {session_id}/
│       ├── document.pdf
│       └── report.docx
├── xlsx_upload/           ← 기존: XlsxWorker 작업용 (7일)
│   └── {session_id}/
│       └── data.xlsx
├── chromadb_user/         ← ChromaDB 임베딩 (7일)
└── ...output dirs...      ← 생성 파일 (1년)
```

### ChromaDB 고아 디렉토리 정리
`delete_collection()`은 sqlite 메타데이터만 삭제하고 디스크의 HNSW 벡터 인덱스 디렉토리를 남기는 ChromaDB 버그가 있음.
`_cleanup_orphan_dirs()` 함수가 매 스케줄 실행 시 `segments` 테이블에 없는 UUID 디렉토리를 자동 삭제.

- 대상: `chromadb_user/` 하위 UUID 디렉토리 중 `segments` 테이블에 없는 것
- 안전장치: UUID 형식 디렉토리만 삭제 (chroma.sqlite3 등 보호)
- 초기 상태: 200개 고아 디렉토리 (~7.86GB) 존재 → 다음 스케줄러 실행 시 정리

## 결정 사항 및 주의점
- XLSX는 `user_uploads/`와 `xlsx_upload/` 양쪽에 저장됨 (보관용 + XlsxWorker 작업용)
- 백엔드 cleanup API 엔드포인트는 유지 (관리/디버깅 용도)
- 7일 보관으로 ChromaDB 디스크 사용량 증가 가능 → 모니터링 필요
- 워크스페이스 파일은 영향 없음 (별도 생명주기)
