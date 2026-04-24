# 2026-04-24 개발서버 Outline 동기화 비활성화 (dev 서버 뻗음 1차 대응)

## 개요
하루 이상 실행된 개발서버(8099 uvicorn 단일 프로세스)가 반복적으로 뻗는 문제의 원인을 `logs/outline_sync.log`에서 확인: **Windows 페이징 파일 고갈(os error 1455)** 로 BGE-m3-ko 모델 CUDA 재로드가 끝없이 실패하며 로그·메모리 폭주. 트리거는 `OUTLINE_SYNC_ENABLED` 환경변수 미설정 시 기본값 `true`로 4시간마다 delta sync가 도는 구조 + `OutlineWebhookService`가 환경변수 가드 없이 무조건 기동되던 점. 운영(blue/green)은 정상 사용 경로이므로 그대로 두고, **dev에서만 두 기능을 OFF** 하도록 1차 조치.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/.env` | 수정 | `OUTLINE_SYNC_ENABLED=false`, `OUTLINE_WEBHOOK_ENABLED=false` 추가 (dev 전용) |
| `backend/app/main.py` | 수정 | `OutlineWebhookService` 기동 블록을 `OUTLINE_WEBHOOK_ENABLED` 가드로 감싸고, shutdown 경로에서 `None` 체크 추가 |

## 상세 내용

### 원인 증거 (logs/outline_sync.log 꼬리)
```
[BEDROCK] generate_text_haiku: us.anthropic.claude-haiku-4-5-20251001-v1:0  × 수십 회
[TOKEN_LOG] outline_sync | haiku | in=... out=...                           × 수십 회
[ChromaDB] CUDA available! Using GPU: NVIDIA GeForce RTX 3070
[ChromaDB] Loading model directly on cuda...
[ChromaDB] Failed to load dragonkue/BGE-m3-ko (attempt 1): 페이징 파일이 너무 작습니다. (os error 1455)
[ChromaDB] Failed to load dragonkue/BGE-m3-ko (attempt 2): 페이징 파일이 너무 작습니다. (os error 1455)
[OutlineSync] ChromaDB upsert 실패: BGE-m3-ko 모델 로드 실패. ... 폴백하지 않습니다.
```
같은 `CUDA available! / Loading model directly on cuda...` 블록이 **매 요청마다 반복** — 모델 싱글톤이 깨진 채 재로드가 무한 시도되고 있었음.

### 트리거 구조
- `outline_sync_scheduler.py:22` : `ENABLED = lambda: os.getenv("OUTLINE_SYNC_ENABLED", "true").lower() == "true"` — **기본값 true** 라 dev .env에 명시가 없으면 항상 돌았음
- `main.py:168-172` : `OutlineWebhookService`는 환경변수 체크 없이 항상 `.start()` 호출 → webhook이 들어오면 embedding 트리거

### 수정 내용
1. `backend/.env` (dev 전용)
   ```
   # Outline Wiki 동기화 (개발서버 비활성화 — 장시간 실행 시 페이징 파일 고갈로 서버 뻗음)
   # 운영서버에서만 실행. 운영 .env는 기본값(true) 사용.
   OUTLINE_SYNC_ENABLED=false
   OUTLINE_WEBHOOK_ENABLED=false
   ```
2. `backend/app/main.py` — Outline Webhook 기동 블록
   ```python
   _outline_webhook_service = None
   if os.getenv("OUTLINE_WEBHOOK_ENABLED", "true").lower() == "true":
       print("[STARTUP] Outline Webhook Service starting...")
       from app.services.outline_webhook_service import get_outline_webhook_service
       _outline_webhook_service = get_outline_webhook_service()
       _outline_webhook_service.start()
   else:
       print("[STARTUP] Outline Webhook Service SKIPPED (OUTLINE_WEBHOOK_ENABLED=false)")
   ```
   shutdown에서도 `if _outline_webhook_service: _outline_webhook_service.stop()`로 가드.

### 운영 영향 확인
- `C:/Services/LFChatbot_prod/blue/backend/.env`, `green/.env` 에는 `OUTLINE_SYNC_ENABLED` · `OUTLINE_WEBHOOK_ENABLED` 변수 자체가 없음 → 기본값 `true` 유지 → **운영 동기화 경로는 영향 없음**.

## 결정 사항 및 주의점

- **이번 커밋은 1차 대응(완화)만**. 진짜 근본 원인은 두 가지가 남아 있음:
  1. `chromadb_service.py`의 BGE-m3-ko 재로드 루프 — 로드 실패 시 backoff·cool-down 없이 매번 재시도 → 로그·페이징 파일 폭주. 실패 후 일정 시간은 즉시 503 반환하도록 후속 개선 필요.
  2. Windows 페이징 파일(가상메모리) 크기 — RTX 3070 8GB + 모델 상주 + Python 힙 구조상 32GB+ 권장.
- `OUTLINE_WEBHOOK_ENABLED` 기본값을 `true`로 둔 건 운영 .env 무변경을 위한 의도적 선택. prod는 변수 미설정이므로 기존 동작 그대로.
- dev에서 Outline 검색 기능(`OutlineWorker`) 자체는 조회 경로라 여전히 정상. 이번에 끈 건 **인덱싱(쓰기) 경로** 뿐.
- 적용 후 dev를 재시작하면 STARTUP 로그에 다음 두 줄이 나와야 정상:
  ```
  [OutlineSyncScheduler] Disabled via OUTLINE_SYNC_ENABLED env
  [STARTUP] Outline Webhook Service SKIPPED (OUTLINE_WEBHOOK_ENABLED=false)
  ```
