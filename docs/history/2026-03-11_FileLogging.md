# 2026-03-11 서버 로그 파일 출력

## 개요
서버 콘솔 로그를 파일로도 동시 출력하여, 별도 터미널에서 실시간 로그를 모니터링할 수 있도록 함.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/main.py | 수정 | RotatingFileHandler + _TeeWriter 추가 |
| bat/start_backend.bat | 신규 | 백엔드 서버 실행 스크립트 |
| bat/tail_log.bat | 신규 | 실시간 로그 뷰어 스크립트 |

## 상세 내용

### 로깅 구조
- `RotatingFileHandler` → `backend/logs/server.log`에 기록
- `_TeeWriter` 클래스가 `sys.stdout`/`sys.stderr`를 래핑하여 `print()` 출력도 로그 파일에 복제
- 콘솔 출력은 기존과 동일하게 유지

### 로그 로테이션
- 파일 크기: 10MB 단위 로테이션
- 백업 수: 최대 5개 (`server.log.1` ~ `server.log.5`)
- 최대 디스크 사용: ~50MB
- 인코딩: UTF-8

### 로그 포맷
```
[2026-03-11 17:14:58] INFO    print | [STARTUP] FastAPI Server Starting...
```

### 실시간 모니터링
- `bat/tail_log.bat` 실행 → PowerShell `Get-Content -Wait -Tail 50`으로 실시간 스트리밍
- UTF-8 인코딩 명시 (`[Console]::OutputEncoding = UTF8`)

## 결정 사항 및 주의점
- 파이프(`tee`) 방식은 Windows에서 Python 출력 버퍼링 문제로 서버 실행 자체가 안 됨 → Python 내부 로깅으로 전환
- `_TeeWriter`에 `fileno()`, `isatty()` 위임 필수 (uvicorn/subprocess 호환)
- `logs/` 디렉토리는 `.gitignore`에 추가 권장
