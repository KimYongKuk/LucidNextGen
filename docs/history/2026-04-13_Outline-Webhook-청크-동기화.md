# 2026-04-13 Outline Wiki Webhook + 청크 기반 동기화

## 개요
Outline Wiki 시멘틱 검색 동기화를 기존 30분 폴링 + Haiku 요약 방식에서 **Webhook 기반 실시간 + 청크 분할 임베딩** 방식으로 전면 개편. 개발서버 GPU OOM 크래시 해결 및 검색 품질 개선.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/services/outline_sync_service.py` | 대폭 수정 | Haiku 요약 제거, 청크 분할 로직, 단건 처리, 시멘틱 검색 문서 그룹핑 |
| `backend/app/services/outline_webhook_service.py` | 신규 | asyncio.Queue 기반 순차 처리 서비스 (GPU OOM 방지) |
| `backend/app/api/routes/outline_webhook.py` | 신규 | Outline webhook 수신 엔드포인트 + 서명 검증 |
| `backend/app/api/routes/outline_sync.py` | 수정 | delta sync, 단건 재인덱싱 API 추가 |
| `backend/app/utils/outline_sync_scheduler.py` | 수정 | 30분 폴링 → 4시간 폴백 delta sync |
| `backend/app/agents/workers/outline_worker.py` | 수정 | 시멘틱 검색 결과 summary → snippet(청크) 대응 |
| `backend/app/main.py` | 수정 | webhook 서비스 등록, 라우터 배선 |
| `backend/.env` | 수정 | VOC_WIKI_SYNC_ENABLED=false (개발서버) |

## 상세 내용

### 기존 문제
- 30분마다 전체 문서 조회 + Haiku 요약 + 일괄 임베딩
- RTX 3070 (8GB) GPU 메모리 고갈 → 서버 크래시 (매일 아침 06:00)
- 본문 앞 3,000자만 요약 → 뒷부분 검색 불가
- 변경 없어도 매회 API 호출 + 메타데이터 로드

### 새 아키텍처

```
[문서 변경 시]
  Outline webhook → FastAPI 수신 → asyncio.Queue
  → Worker (단일 소비자, 1건씩):
      1. 기존 청크 삭제 (document_id 기준)
      2. 본문 청크 분할 (600자, 100자 오버랩, 한국어 문장 경계)
      3. 청크별 임베딩 → ChromaDB upsert (8건 소배치)
  → 완료 (~3초)

[검색 시]
  시멘틱 검색 → 청크 매칭 → document_id 그룹핑
  → 최고 스코어 청크 기준 문서 순위 결정
  → 키워드 검색과 RRF 병합

[안전장치]
  4시간마다 폴백 delta sync (놓친 webhook 보완)
```

### 청크 분할 로직
- 마크다운 제거 후 순수 텍스트 변환
- `RecursiveCharacterTextSplitter` + 한국어 분리자 (`다. `, `요. `, `까? ` 등)
- 청크 크기: 600자, 오버랩: 100자
- 각 청크에 `# {제목}\n\n` 접두사 → 임베딩 시 문서 맥락 유지
- ChromaDB ID: `{document_id}_chunk_{index}`

### Webhook 서비스
- `asyncio.Queue(maxsize=500)` + 단일 소비자 태스크
- 중복 제거: 같은 document_id가 큐에 있으면 스킵 (삭제 이벤트는 항상 처리)
- 서명 검증: `OUTLINE_WEBHOOK_SECRET` 환경변수 (미설정 시 스킵)
- 지원 이벤트: documents.create/update/publish/delete/archive/unarchive

### API 엔드포인트

| 엔드포인트 | 용도 |
|-----------|------|
| `POST /api/v1/webhooks/outline` | Outline webhook 수신 |
| `GET /api/v1/webhooks/outline/status` | webhook 큐 상태 조회 |
| `POST /api/v1/admin/outline-sync/trigger` | 전체 재인덱싱 (백그라운드) |
| `POST /api/v1/admin/outline-sync/delta` | delta sync (최근 변경분) |
| `POST /api/v1/admin/outline-sync/reindex/{id}` | 단건 재인덱싱 |

### 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OUTLINE_WEBHOOK_SECRET` | (빈값) | webhook 서명 검증용 시크릿 |
| `OUTLINE_SYNC_INTERVAL_MINUTES` | `240` | 폴백 delta sync 주기 (분) |
| `VOC_WIKI_SYNC_ENABLED` | `true` | VOC Wiki 스케줄 on/off |

## 결정 사항 및 주의점
- Haiku 요약 제거 → LLM 비용 0, 파이프라인 단순화
- 청크 방식으로 본문 전체 검색 가능 (기존: 앞 3,000자 요약만)
- GPU OOM 방지: 임베딩 소배치(8건) + 순차 처리(큐 단일 소비자)
- 초기 적재: 배포 후 `POST /api/v1/admin/outline-sync/trigger`로 전체 재인덱싱 필요
- 기존 ChromaDB 데이터: ID 형식 변경(`{doc_id}` → `{doc_id}_chunk_{N}`)으로 자연 교체
- Outline 관리자에서 webhook 설정 필요: URL, 이벤트, 시크릿
- 개발서버 VOC Wiki Sync 비활성화 (`VOC_WIKI_SYNC_ENABLED=false`)
