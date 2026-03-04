# 2026-02-27 파일 정리 스케줄러 통합

## 개요

기존 PDF 전용 정리 스케줄러(`pdf_cleanup.py`)를 범용 파일 정리 스케줄러(`file_cleanup.py`)로 확장. 하나의 스케줄러가 PDF, PPT, 차트, XLSX 출력 디렉토리 및 XLSX 업로드 디렉토리를 순회하며 보관 기간이 지난 파일을 자동 삭제한다.

---

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/utils/file_cleanup.py` | **신규** | 범용 파일 정리 스케줄러 (5개 디렉토리 순회) |
| `backend/app/utils/pdf_cleanup.py` | **삭제** | 기존 PDF 전용 스케줄러 제거 |
| `backend/app/main.py` | 수정 | import 변경 (`pdf_cleanup_scheduler` → `file_cleanup_scheduler`) |

---

## 1. file_cleanup.py 구조

### 정리 대상

| 디렉토리 | 패턴 | 비고 |
|----------|------|------|
| `data/pdf_output/` | `*.pdf` | PDF 생성물 |
| `data/ppt_output/` | `*.pptx` | PPT 생성물 |
| `data/chart_output/` | `*.png` | 차트 이미지 |
| `data/xlsx_output/` | `*.xlsx` | XLSX 생성/수정물 |
| `data/xlsx_upload/` | `**/*.xlsx` | 사용자 업로드 원본 (재귀 탐색, 빈 하위 디렉토리 자동 제거) |

### 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `FILE_RETENTION_HOURS` | `8760` (1년) | 파일 보관 기간 (시간) |
| `FILE_CLEANUP_INTERVAL_HOURS` | `24` | 정리 스캔 실행 주기 (시간) |

### 동작 방식

1. 서버 시작 시 `file_cleanup_scheduler.start()` 호출
2. 시작 즉시 1회 실행 + 이후 `FILE_CLEANUP_INTERVAL_HOURS` 간격으로 반복
3. 각 대상 디렉토리의 파일 `mtime`을 확인하여 `FILE_RETENTION_HOURS` 초과 시 삭제
4. `xlsx_upload/`은 재귀 패턴(`**/*.xlsx`)으로 하위 세션 디렉토리까지 탐색
5. 파일 삭제 후 빈 하위 디렉토리(`remove_empty_dirs: True`)는 자동 제거
6. 삭제 결과를 로그에 기록 (`[File Cleanup]` 태그)

### 주요 함수/클래스

```
cleanup_old_files(retention_hours=None) → dict
├── CLEANUP_TARGETS 순회
├── glob 패턴 매칭
├── mtime < cutoff → unlink
├── remove_empty_dirs 처리
└── return {deleted, errors, total_size_kb}

FileCleanupScheduler
├── start(interval_hours=None)  # APScheduler 등록 + 즉시 1회 실행
├── stop()                       # 스케줄러 종료
└── run_now() → dict             # 수동 즉시 실행

file_cleanup_scheduler  # 전역 싱글턴 인스턴스
```

---

## 2. main.py 변경

```diff
- from app.utils.pdf_cleanup import pdf_cleanup_scheduler
+ from app.utils.file_cleanup import file_cleanup_scheduler

# lifespan 내부
- print("[STARTUP] PDF Cleanup Scheduler starting...")
- pdf_cleanup_scheduler.start()
+ print("[STARTUP] File Cleanup Scheduler starting...")
+ file_cleanup_scheduler.start()

# shutdown
- pdf_cleanup_scheduler.stop()
+ file_cleanup_scheduler.stop()
```

---

## 3. 기존 대비 변경점

| 항목 | 기존 (pdf_cleanup.py) | 변경 후 (file_cleanup.py) |
|------|----------------------|--------------------------|
| 대상 | PDF만 (`data/pdf_output/*.pdf`) | 5개 디렉토리 (PDF, PPT, 차트, XLSX, 업로드) |
| 보관 기간 | 24시간 | 1년 (8760시간) |
| 정리 주기 | 6시간 | 24시간 |
| 환경변수 | `PDF_RETENTION_HOURS`, `PDF_CLEANUP_INTERVAL_HOURS` | `FILE_RETENTION_HOURS`, `FILE_CLEANUP_INTERVAL_HOURS` |
| 빈 디렉토리 정리 | 없음 | `xlsx_upload/` 하위 빈 디렉토리 자동 제거 |

---

## 4. 관련 스케줄러 전체 현황

| 스케줄러 | 파일 | 대상 | 기본 보관 | 기본 주기 |
|----------|------|------|----------|----------|
| `file_cleanup_scheduler` | `file_cleanup.py` | 출력 파일 (PDF/PPT/차트/XLSX) | 1년 | 24시간 |
| `session_cleanup_scheduler` | `chromadb_cleanup.py` | ChromaDB session_* 컬렉션 | 24시간 | 6시간 |
