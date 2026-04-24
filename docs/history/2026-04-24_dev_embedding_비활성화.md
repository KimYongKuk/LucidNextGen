# 2026-04-24 개발서버 BGE-m3-ko 임베딩 로드 차단 (운영과의 GPU·커밋 경합 제거)

## 개요
같은 Windows 호스트에서 dev 백엔드(8099)와 운영 blue/green(8001/8002)이 각자 `PyTorch+CUDA+BGE-m3-ko+ChromaDB`를 로드하며 **프로세스당 peak Virtual ~95GB**를 예약 → 시스템 commit limit(93GB = 물리 64GB + 페이징 29GB) 경계를 넘나드는 구조적 경합이 드러남. 오늘 조사에서 dev가 좀비화되면 95GB를 그대로 쥐고 있는 PID가 확인됐고, 운영 green도 PeakVirtualMB 96,880MB 기록. 즉 "한 프로세스만 돌려도 한계에 닿고 두 개면 터지는" 상태. 페이징 상향은 C드라이브 여유(29GB) 문제로 어려움. **근본 원인을 제거하기 위해 dev에서만 임베딩 모델 로드 자체를 차단**하여 dev 백엔드가 RAG/벡터 경로에 자원을 쓰지 않도록 함.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/.env` | 수정 | `DEV_DISABLE_EMBEDDING=true` 추가 (dev 전용) |
| `backend/app/services/chromadb_service.py` | 수정 | `SafeSentenceTransformerEmbeddingFunction._load_model()` 초입에 플래그 가드 추가 → true면 즉시 `RuntimeError` |

## 상세 내용

### 조사로 확보한 증거
- **dev 좀비 프로세스** (오늘 관찰, 이후 수동 종료):
  - PID 1543848, `python app/main.py`, Virtual **95,374 MB** (9.3× prod 대비)
  - 시스템 FreeVirtual 1.9GB까지 떨어져 `[ChromaDB] Failed to load ... os error 1455` 재발
- **운영 green 프로세스**도 PeakVirtualMB **96,880 MB** 기록 — 같은 패턴
- ENABLED 플래그 비교 결과, dev가 오히려 prod보다 기능을 덜 돌림에도 동일 peak → **기능 활성화가 아니라 PyTorch/CUDA 로드 자체가 주범**
- Windows 호스트 스펙: 물리 64GB + 페이징 29.7GB + C드라이브 여유 29GB (페이징 대폭 상향 불가)

### 왜 "임베딩 로드만 막아도" 근본 해결인가
BGE-m3-ko 로드 직전 PyTorch DLL만으로도 Virtual ~3.5GB이 예약되지만, **95GB까지 부풀리는 주 원인은 safetensors mmap + CUDA caching allocator + cuDNN 엔진 컴파일 예약의 조합**. 이 조합은 `SentenceTransformer(...)` 호출 시점부터 시작됨. `_load_model()`을 차단하면 이 예약이 일어나지 않아 **dev 백엔드 peak가 10GB 전후 수준에서 유지**될 것으로 예상 (PyTorch import만의 기본선).

### 구현

#### 1. `chromadb_service.py`
`_load_model()` 초입, 이미 로드된 모델이 있는지 검사한 직후에 플래그 체크:
```python
def _load_model(self):
    if self._model is not None:
        return self._model

    if os.getenv("DEV_DISABLE_EMBEDDING", "false").lower() == "true":
        raise RuntimeError(
            "임베딩이 DEV_DISABLE_EMBEDDING=true로 비활성화되었습니다. "
            "개발서버에서 운영과의 GPU·커밋 차지 경합 방지용 설정입니다. "
            "RAG 검색·파일 벡터화를 사용하려면 .env에서 이 플래그를 제거하세요."
        )

    with _model_load_lock:
        ...  # 기존 로드 로직
```

#### 2. `backend/.env` (dev 전용)
```
DEV_DISABLE_EMBEDDING=true
```

### 파급 범위 (dev에서 비활성화되는 기능)
- `search_user_files`, `search_workspace_docs`, `search_hr/ac/it/safety_docs` — 호출 시 명확한 RuntimeError
- 파일 업로드 시 벡터화 단계 — 업로드 자체는 디스크 저장까지 진행 후 임베딩 단계에서 실패 처리
- Outline Wiki 시멘틱 검색 (`OutlineWorker.semantic_search`) — 이미 OUTLINE_SYNC/WEBHOOK도 OFF

### 정상 동작하는 것
- Bedrock 기반 채팅 스트리밍, Haiku/Sonnet 호출
- 메일/결재/캘린더/예약/NAS/조직도/엑셀/PDF/차트 등 임베딩 불필요한 모든 Worker
- 워크스페이스/세션 관리, 인증, 사용자 메모리 등
- MCP `rag_server.py` 서브프로세스는 부모 환경변수를 상속받아 같은 차단 적용

### 운영 영향
- `C:/Services/LFChatbot_prod/blue/backend/.env`, `green/.env`에는 `DEV_DISABLE_EMBEDDING` 변수 미설정 → 기본값 `false` → **운영 영향 없음**

## 결정 사항 및 주의점

- **플래그 이름에 `DEV_`를 붙임**: 운영 .env에 실수로 들어가도 이름 자체가 개발용임을 드러내므로 눈에 띄고, CHANGELOG에 방어 표기 남기기 용이.
- **재시작 후 기대 동작**: dev 백엔드 기동 로그에 `[ChromaDB] CUDA available!`가 **애초에 찍히지 않음**. 첫 RAG 호출 시에만 RuntimeError 로그 1회 발생 후, 사용자 응답에는 기존 에러 핸들링 경로를 통해 "검색 중 오류 발생 — 임베딩이 비활성화되었습니다" 식으로 전달됨.
- **되돌리는 방법**: `.env`의 `DEV_DISABLE_EMBEDDING` 줄을 지우거나 `false`로 바꾸면 재기동 후 즉시 복귀. 프로세스 경합이 필요 없는 시점(예: 운영 서버가 잠시 중단된 상황에서 dev에서 RAG 테스트해야 할 때)에만 토글.
- **근본적으로 더 깔끔한 선택지**는 MCP `rag_server.py`가 자체 ChromaDBService를 들지 않고 메인 백엔드의 내부 REST 엔드포인트를 호출하는 구조 개선. 이번 조치는 "dev에서 경합을 없애는" 국소 해결이며, 구조 개선은 별건의 과제로 남김.
- **사용자 UX**: dev에서 RAG 관련 질의를 하면 에러가 뜨지만, 본 서비스(운영)는 영향 없음. dev 테스트 시 RAG가 꼭 필요한 경우 플래그 제거 후 짧게 테스트하고 복구.
