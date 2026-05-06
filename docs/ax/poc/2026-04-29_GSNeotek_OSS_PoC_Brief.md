# GS네오텍 오픈소스 LLM PoC 자료 — Lucid AI 챗봇

작성일: 2026-04-29
작성자: 김용국
대상: GS네오텍 (PoC 지원 협력업체)
목적: AWS EC2 GPU 환경에서 오픈소스 LLM(예: DeepSeek V4, GPT-OSS 120B 등)을 검토하기 위한
**테스트 시나리오** 및 **현 운영 사용량** 공유

---

## 1. PoC 목표 요약

| 구분 | 현재(Bedrock) | PoC 대상(OSS on EC2) |
|------|---------------|----------------------|
| **빠른 분류·메모리** | Claude **Haiku 4.5** | 우선 대체 대상 — 비용·지연 최적화 |
| **고급 추론·툴 호출** | Claude **Sonnet 4.5** | 일부 워커 한정 비교 평가 |
| **임베딩/RAG** | BGE-M3 (Sentence Transformers, 자체 호스팅) | 변경 없음 |

핵심 가치 가설:
- **Haiku 호출 트래픽(분류/메모리/타이틀/요약)** 은 짧고 정형화된 in/out → 8B~30B급 OSS로 충분 가능
- **Sonnet 호출 트래픽(워커 본문)** 은 한국어 추론·도구 호출·긴 컨텍스트 — 70B+ MoE 모델 후보
  (DeepSeek V4 / Qwen3-235B-A22B / GPT-OSS 120B 등)

PoC 평가 1순위: **Haiku → OSS 교체**, 2순위: 고난도 워커(Direct, Mail, WebSearch)에서 Sonnet 비교

---

## 2. 시스템 아키텍처 개요 (LLM 호출 지점)

```
[사용자 메시지]
    │
    ▼
[Phase 1] intent_classifier  ──► **Haiku** (rule-based 우회 불가 케이스만)
    │   in≈4K / out≈5 토큰, p50 < 1.5s
    ▼
[Phase 2] Worker 라우팅 (18개 워커 중 1개 선택)
    │
    ▼
[Worker 실행 — Sonnet, 일부 도구 호출 루프]
    ├── DirectResponseWorker      (일반 대화)
    ├── WebSearchWorker            (Tavily)
    ├── UserFilesWorker            (개인 업로드 RAG)
    ├── CorpRAGWorker              (HR/안전 규정 RAG)
    ├── MailWorker                 (사내 메일 조회/요약)
    ├── XlsxWorker                 (엑셀 생성/수정)
    ├── PPTWorker                  (PPT 생성)
    ├── PlannerExecutor            (멀티스텝 분해)
    ├── ApprovalWorker             (전자결재 SQL/조회)
    ├── ITSupportWorker            (IT VOC + 규정)
    ├── AcctSupportWorker          (회계 VOC + 규정)
    ├── CalendarWorker             (그룹웨어 캘린더)
    ├── ReservationWorker          (회의실 예약)
    ├── BoardWorker                (사내 게시판)
    ├── OutlineWorker              (사내 위키)
    ├── NASWorker                  (공유 스토리지)
    ├── URLFetchWorker             (URL 추출)
    └── YouTubeWorker              (영상 요약)
    │
    ▼
[백그라운드 비동기]  ──► **Haiku**
    ├── memory_ws_summary          (워크스페이스 롤링 요약, 10턴마다)
    ├── memory_ws_facts            (워크스페이스 핵심 사실)
    ├── memory_user_facts          (사용자 글로벌 메모리, 20턴마다)
    ├── memory_user_consolidation  (사실 100개 초과 시 압축)
    └── outline_sync / voc_wiki_*  (배치 분류·머지)

[다른 비동기]  ──► **Sonnet 또는 Haiku (fallback)**
    └── title_generation           (세션 첫 메시지 후 제목 생성)
```

**관측 포인트**: 모든 LLM 호출은 `token_usage_log` 테이블에 caller / model_id /
in·out·cache 토큰 단위로 기록되어, PoC 비교 시 동일 기준 평가 가능.

---

## 3. 테스트 시나리오 — 워커별 입출력 패턴

> 표의 토큰 통계는 운영 환경 50일(2026-03-10 ~ 2026-04-29) 실측치 평균값입니다.
> "복잡도" 는 도구 호출 루프, 한국어 도메인 지식, 포맷팅 정확도 요구 수준 종합 평가.

### 3.1 Haiku 트래픽 (PoC 1순위 — 대체 평가)

| Caller | 호출수<br>(50일) | 평균 in | 평균 out | 최대 in | 복잡도 | OSS 후보 검증 시나리오 |
|---|---:|---:|---:|---:|---|---|
| **intent_classifier** | 9,075 | 6,156 | 5 | 196,052 | ★★★★ (라우팅 정확도가 시스템 품질 결정) | 19개 intent 중 1개 선택. 한국어 키워드 + 영어 시스템명 혼재. JSON 출력 강제. |
| **memory_user_facts** | 659 | 13,274 | 88 | 73,553 | ★★★ (사용자 신원 보존, fact 압축) | 대화 5쌍 → 핵심 사실 1~3개 추출. `[업데이트] old → new` 문법. |
| **memory_ws_summary** | 69 | 6,701 | 539 | 31,995 | ★★ (롤링 요약, 500자 이내) | 워크스페이스 대화 10턴 → 500자 요약 갱신. |
| **memory_ws_facts** | 69 | 6,875 | 247 | 32,244 | ★★ | 워크스페이스 핵심 사실 추출 (도메인 정보 위주). |
| **outline_sync** | 197 | 1,097 | 227 | — | ★ | 위키 문서 메타데이터 분류. |
| **voc_wiki_classify / merge** | 218 | 1,865~2,447 | 41~1,482 | — | ★★ | VOC → 위키 자동 등록 분류·머지. |
| **title_generation** (fallback) | 29 | 200 | 20 | 439 | ★ (짧음) | 첫 사용자 메시지 → 30자 이내 한국어 제목. |

**시나리오 셋(Haiku):**
1. **Intent 분류 100선** — 모드(개인/워크스페이스), 파일 업로드 유무, 워크스페이스 지시문 등
   컨텍스트 변수 조합. 정답 라벨 보유. **목표: F1 ≥ 0.92, p95 응답 < 1.5s**.
2. **메모리 추출 50선** — 다양한 직군(개발/회계/IT/HR) 5턴 대화 → 핵심 사실 추출.
   **목표: 신원정보 손실 0건, 무관 정보 추출률 < 10%**.
3. **요약 30선** — 워크스페이스 10턴 → 500자 한국어 요약. **목표: 사실 정합성 ≥ 95%**.

### 3.2 Sonnet 트래픽 (PoC 2순위 — 고난도 워커 비교)

| Worker | 호출수<br>(50일) | 평균 in | 평균 out | 최대 in | 도구 호출 | 복잡도 |
|---|---:|---:|---:|---:|---|---|
| **DirectResponseWorker** | 6,211 | 2,925 | 1,232 | 118,454 | 일부 (PDF/차트/Word 생성) | ★★★ 일반 추론·코딩·번역·창작 |
| **planner** | 4,336 | 858 | 182 | 38,624 | — (분해만) | ★★★★ 멀티스텝 작업 분해, JSON 출력 |
| **WebSearchWorker** | 2,551 | 12,004 | 1,840 | 184,693 | tavily_search | ★★★ 한국어/영어 검색결과 종합 |
| **MailWorker** | 1,437 | 11,927 | 1,119 | 227,746 | get_inbox/sent/search/detail | ★★★★ 사번 보안·MIME 본문 요약·답장 초안 |
| **UserFilesWorker** | 1,145 | 18,071 | 1,861 | 203,618 | search_user_files / workspace_docs | ★★★★ 긴 RAG 컨텍스트, 출처 인용 |
| **XlsxWorker** | 937 | 15,876 | 1,670 | 154,737 | 24개 엑셀 도구 (write/format/formula) | ★★★★★ 도구 루프 + 한국어 표 구조 |
| **CorpRAGWorker** | 878 | 4,379 | 904 | 57,322 | search_hr/safety_docs | ★★★ HR/안전 규정 RAG |
| **PPTWorker** | 762 | 16,287 | 4,916 | 87,867 | 슬라이드 생성 도구 | ★★★★★ 긴 출력 + 표/시각화 결정 |
| **ApprovalWorker** | 726 | 7,191 | 1,319 | 99,865 | execute_approval_query | ★★★★ PostgreSQL 9 VIEW SQL 생성 |
| **CalendarWorker** | 597 | 4,354 | 588 | 58,601 | get/create/delete events | ★★★ |
| **ITSupportWorker** | 506 | 4,842 | 1,080 | 27,520 | search_it_docs + voc_query + register | ★★★★ |
| **BoardWorker** | 306 | 5,481 | 1,083 | 20,822 | board_search SQL | ★★★ |
| **AcctSupportWorker** | 236 | 6,243 | 1,306 | 27,492 | search_ac_docs + voc_query | ★★★★ |
| **OutlineWorker** | 236 | 14,691 | 863 | 109,867 | outline_search/publish | ★★★ |
| **VisualizationWorker** | 131 | 13,572 | 2,610 | — | PDF/차트 도구 | ★★★ |
| **ReservationWorker** | 87 | 2,885 | 388 | — | reservation 도구 | ★★ |
| **URLFetchWorker** | 60 | 11,814 | 1,425 | 24,346 | fetch | ★★★ |
| **NASWorker** | 24 | 4,404 | 1,149 | 5,308 | nas_search | ★★ |
| **YouTubeWorker** | 8 | 2,172 | 631 | 2,490 | youtube_summarize | ★★ |

**시나리오 셋(Sonnet):**
1. **Direct 응답 30선** — 코딩(Python/SQL), 번역, 수학, 창작, 한국어 비즈니스 작문.
   **품질 평가: 인간 평가자 4명 1~5점 채점**.
2. **WebSearch 종합 20선** — 한국 산업 동향, 회사 정보, 규제 검색 후 요약 + 출처.
   **목표: 출처 누락 ≤ 5%**.
3. **도구 루프 안정성** — XlsxWorker 30선 (10시트 생성, 수식, 서식),
   PPTWorker 20선 (10슬라이드 + 표/차트), MailWorker 30선 (조회 → 본문 → 요약 → 답장).
   **목표: 도구 호출 성공률 ≥ 95%, 평균 호출 횟수 현재 대비 +20% 이내**.
4. **장문 RAG 일관성** — UserFilesWorker 20선 (PDF 30~100페이지 업로드 후 사실 질의).
   **목표: 환각률 < 3%**.
5. **SQL 생성 정확도** — ApprovalWorker / BoardWorker / IT·Acct VOC SQL 50선.
   **목표: 실행 가능 SQL ≥ 98%, 결과 정합성 ≥ 90%**.

### 3.3 PoC 시 측정해야 할 공통 지표

| 지표 | 측정 방법 | 합격 기준(현 Haiku/Sonnet 대비) |
|---|---|---|
| 응답 정확도 | 정답셋 매칭 / 인간 평가 (1~5) | ≥ 90% 또는 평균 4.0 이상 |
| 한국어 자연성 | 인간 평가 | 평균 ≥ 4.0 |
| **TTFT** (Time-To-First-Token) | 스트리밍 첫 토큰 도달 시간 | Haiku≤1s, Sonnet≤3s |
| **출력 속도** | tokens/sec | ≥ 30 t/s (스트리밍 체감) |
| 도구 호출 성공률 | 비도구→도구 정상 분기 + 인자 유효성 | ≥ 95% |
| JSON 출력 강제 준수 | 스키마 매치 | ≥ 98% |
| GPU VRAM 점유 | nvidia-smi | 모델별 표기 |
| 동시 동시 처리량 | wrk/k6, 동시 N | 분당 30 RPM, 동시 7 user 견딤 |

---

## 4. 사용량 수준 (운영 환경 실측, 50일)

### 4.1 사용자 / 메시지 볼륨

| 지표 | 값 |
|---|---:|
| 측정 기간 | 2026-03-10 ~ 2026-04-29 (50일) |
| **DAU** (전일) | 244명 |
| **WAU** (7일) | 310명 |
| **MAU** (30일) | **438명** |
| 30일 메시지 | 11,217건 |
| 7일 메시지 | 3,028건 |
| 일평균 메시지 (영업일) | **약 500~850건** |
| **피크일 메시지 (4/28)** | 844건 / 171 unique users |

> 주말·공휴일은 트래픽이 1/100 수준으로 떨어짐. 피크 시간대는 **평일 11시~16시**.
> 동시 활성 사용자(분당 unique) 최대값은 **7명** (4/28 11:46).

### 4.2 LLM 호출 볼륨

| 모델 | 50일 누적 호출 | 점유율 | 입력토큰 | 출력토큰 | 캐시 read | 캐시 write |
|---|---:|---:|---:|---:|---:|---:|
| **Sonnet 4.5** | 27,178 | 72% | 143.1M | 26.3M | 195.7M | 101.3M |
| **Haiku 4.5** | 10,316 | 28% | 48.2M | 0.41M | 0 | 0 |
| **합계** | **37,494** | 100% | **191.3M** | **26.7M** | 195.7M | 101.3M |

* Sonnet 캐시 히트율 ≈ **58%** (cache_read / 총 인풋 추정) — Bedrock prompt caching 적극 사용.
* 메시지 1건당 평균 LLM 호출수: 37,494 / 11,217 ≈ **3.3 calls/msg** (intent + planner + worker + memory).

### 4.3 일별 호출 추이 (직전 14일)

| 날짜 | Haiku calls | Sonnet calls | 합계 |
|---|---:|---:|---:|
| 2026-04-29 | 25 | 1,515 | 1,540 |
| 2026-04-28 | 65 | 2,221 | **2,286** ← 피크 |
| 2026-04-27 | 30 | 1,205 | 1,235 |
| 2026-04-24 | 16 | 912 | 928 |
| 2026-04-23 | 17 | 769 | 786 |
| 2026-04-22 | 25 | 1,294 | 1,319 |
| 2026-04-21 | 23 | 1,356 | 1,379 |
| 2026-04-20 | 253 | 1,824 | 2,077 |
| 2026-04-17 | 148 | 456 | 604 |
| 2026-04-16 | 282 | 927 | 1,209 |
| 2026-04-15 | 255 | 799 | 1,054 |
| 2026-04-14 | 419 | 1,081 | 1,500 |
| 2026-04-13 | 309 | 890 | 1,199 |
| 2026-04-10 | 161 | 452 | 613 |

> 4월 후반 Haiku 호출 감소는 intent_classifier의 rule-based quick_classify 적중률 향상 때문.
> **PoC 부하 산정 시 일 호출수 약 2,500건 / 영업시간(8h) 기준 ≈ 5.2 RPM 평균** 사용 권장.

### 4.4 시간대별 분포 (직전 7일, Sonnet 기준)

| 시간 | calls | 시간 | calls |
|---|---:|---|---:|
| 07시 | 157 | 14시 | 552 |
| 08시 | 541 | 15시 | 550 |
| 09시 | 583 | 16시 | 605 |
| 10시 | 634 | 17시 | 482 |
| **11시** | **875** ← 피크 | 18시 | 422 |
| 12시 | 142 (점심) | 19시 | 267 |
| 13시 | 622 | 20시 | 104 |

* **피크 분당 호출수**: 18 calls/min (4/28 11:46, 13:12) — 대부분 Sonnet
* **피크 RPS**: 약 0.3 req/sec (단일 사용자 1턴이 평균 3.3 LLM call로 분기되는 점 고려)

### 4.5 응답시간 (Worker별 30일 평균, ms)

| Worker | calls | 평균 | 최소 | 최대 |
|---|---:|---:|---:|---:|
| ReservationWorker | 78 | 15,383 | 2,880 | 46,548 |
| CalendarWorker | 402 | 17,340 | 2,915 | 103,077 |
| MailWorker | 852 | 27,152 | 2,788 | 248,074 |
| ITSupportWorker | 319 | 27,623 | 3,214 | 126,344 |
| DirectResponseWorker | 4,994 | **27,616** | 3,101 | 800,572 |
| CorpRAGWorker | 363 | 28,263 | 3,264 | 166,800 |
| BoardWorker | 147 | 29,465 | 4,023 | 225,053 |
| OutlineWorker | 119 | 29,714 | 3,387 | 172,773 |
| AcctSupportWorker | 134 | 32,979 | 5,392 | 151,803 |
| ApprovalWorker | 391 | 35,777 | 4,255 | 467,841 |
| URLFetchWorker | 28 | 37,153 | 6,757 | 143,319 |
| XlsxWorker | 446 | 37,271 | 3,385 | 1,452,502 |
| UserFilesWorker | 645 | 39,238 | 2,885 | 363,733 |
| WebSearchWorker | 1,380 | 42,251 | 3,055 | 643,784 |
| Planner-Executor | 418 | 84,629 | 6,299 | 331,891 |
| **PPTWorker** | 474 | **102,306** | 4,031 | 1,017,152 |

> 워커 응답시간 = LLM + 도구 호출(I/O) + 후처리. PPT/XLSX는 도구 루프 비중이 큼.
> **PoC 동등 비교용 KPI**: Direct/Mail/Calendar/Reservation 같은 단순 워커의 평균 응답시간을
> **현재 Sonnet 27초 → OSS 30초 이내** 유지하면 합격선.

### 4.6 Intent 분포 (30일, 워크로드 비중)

| Intent | 호출수 | 점유율 |
|---|---:|---:|
| direct | 4,621 | 41.2% |
| web_search | 1,380 | 12.3% |
| mail | 852 | 7.6% |
| user_files | 645 | 5.7% |
| ppt_generation | 474 | 4.2% |
| xlsx | 446 | 4.0% |
| planner | 418 | 3.7% |
| approval | 391 | 3.5% |
| clarify | 373 | 3.3% |
| corp_rag | 363 | 3.2% |
| it_support | 319 | 2.8% |
| calendar | 306 | 2.7% |
| reservation | 174 | 1.6% |
| board | 147 | 1.3% |
| acct_support | 134 | 1.2% |
| outline | 119 | 1.1% |
| 기타 (url/nas/youtube) | 55 | 0.5% |

* 단순 대화(direct) + 검색(web_search) 이 **53%** — OSS 모델이 가장 먼저 검증해야 할 영역
* 도구 루프 의존 워커(mail/xlsx/ppt/approval/calendar) 합계 약 **24%** — 도구 호출 능력이 결정적

### 4.7 메시지 길이 / 세션 길이

| 항목 | 평균 | 최대 |
|---|---:|---:|
| 사용자 입력 길이 (chars) | 209 | 42,507 |
| 모델 출력 길이 (chars) | 1,472 | 32,952 |

| 세션 메시지 수 | 세션 비율 |
|---|---:|
| 1~2턴 | 67% |
| 3~5턴 | 21% |
| 6~10턴 | 7% |
| 11~20턴 | 3% |
| 21+턴 | 1% |

> 짧은 1~2턴 대화가 다수 → **TTFT가 사용자 체감 품질의 핵심**.

### 4.8 컨텍스트 윈도우 산정

| 항목 | 값 | 시사점 |
|---|---:|---|
| Haiku in 평균 | ~6K | 8K context로 99% 케이스 커버 |
| Haiku in 최대 | 196K | 워크스페이스 메모리 추출 시 발생 |
| Sonnet in 평균 | ~5K | — |
| Sonnet in 최대 | 227K (Mail) | 대용량 메일/엑셀/PDF |
| **권장 OSS 모델 컨텍스트** | **128K 이상** | 32K로 자름시 워크스페이스 시나리오 일부 손실 |

---

## 5. PoC 환경 권장 사양

### 5.1 EC2 GPU 후보

| 모델 후보 | 추론 권장 GPU | EC2 인스턴스 | 비고 |
|---|---|---|---|
| GPT-OSS 120B (MoE 5B active) | A100 80GB ×1 또는 H100 80GB ×1 | g5.48xlarge 또는 p4d/p5 | FP8 양자화 시 단일 GPU |
| DeepSeek V4 (MoE) | H100 80GB ×8 | p5.48xlarge | 풀모델 — 가용성 확인 필요 |
| Qwen3-235B-A22B | H100 80GB ×4 | p5.24xlarge | MoE 22B active |
| Llama 3.3 70B | A100 80GB ×2 | p4d.24xlarge | 한국어 추가학습 모델 권장 |
| Mistral Small 3 (24B) | A10G 24GB ×1 | g5.2xlarge | Haiku 대체 후보 |
| Qwen2.5-32B-Instruct | A100 40GB ×1 | g5.12xlarge | Haiku 대체 후보 |

### 5.2 추론 서버 권장

- **vLLM** 또는 **TGI** (Text Generation Inference) — OpenAI-compatible API 제공
- 우리 백엔드는 이미 `services/openapi_bedrock_service.py` / `api/routes/openapi_compat.py` 통해
  **OpenAI-compatible 엔드포인트 호환** 가능. PoC 시 `BEDROCK_MODEL_ID`만 endpoint 교체하는 식으로
  최소 변경으로 비교 평가 가능.
- 도구 호출(function calling) 지원 모델/서빙 조합 필수.

### 5.3 부하 테스트 시나리오

| 시나리오 | 부하 | 기준 |
|---|---|---|
| Baseline | 5 RPM 지속 30분 | 응답 정상, 평균 RT < 30s |
| Peak | **20 RPM 5분** | 큐 적체 없음, p95 RT < 60s |
| Burst | 50 RPM 1분 | 503 없음, 백프레셔 정상 동작 |
| 동시성 | **동시 7 user × 평균 3턴** | 모든 응답 완주, 메모리 누수 없음 |

> 운영 피크가 분당 18 호출(약 0.3 RPS)이므로, **30 RPM(0.5 RPS)** 처리 가능하면 운영 충분.
> 단, 1년 후 사용자 2배 성장 가정 시 **60 RPM 처리 여유** 확보 권장.

---

## 6. 평가 산출물 (PoC 결과로 받고자 하는 것)

1. **모델별 정량 비교 리포트**
   - Intent 분류 F1 / 메모리 추출 정합성 / 도구 호출 성공률 / TTFT / TPS
2. **도메인 시나리오 100선 결과 매트릭스** (현 Sonnet/Haiku vs OSS 모델 N개)
3. **GPU 사용량·비용 추정** — 운영 트래픽 24시간 시뮬레이션 시 인스턴스 비용
4. **권장 모델 1~2개 + 근거** — Haiku 대체용, Sonnet 대체용 분리 권고
5. **마이그레이션 리스크** — 도구 호출 포맷, JSON 강제, 한국어 안전성 등 known issue

---

## 7. 데이터 제공 가능 항목

| 자료 | 형태 | 비고 |
|---|---|---|
| Intent 분류 정답셋 | JSONL ~500건 | 운영 로그에서 수동 라벨링 |
| 워커별 입출력 샘플 | JSONL ~30건/워커 | PII 마스킹 후 |
| 한국어 도메인 RAG 코퍼스 | 비공개 | 보안 검토 필요 — 일부 일반화 샘플로 대체 가능 |
| 시스템 프롬프트 셋 | 마크다운 | 워커별 프롬프트 17종 |
| 토큰 사용량 raw 로그 | CSV | `token_usage_log` (50일 / 37,494 row) — 사용자 식별자 마스킹 |

---

## 부록 A. 참고 파일

- 모델 설정: `backend/app/core/model_config.py`
- 토큰 로깅: `backend/app/services/token_usage_service.py`
- Intent 분류: `backend/app/agents/intent_classifier.py`
- 워커 구현: `backend/app/agents/workers/*.py`
- 메모리: `backend/app/services/memory_service.py`

## 부록 B. 추출 통계 원본 (재현 가능)

- `c:\tmp\poc_stats\extract_usage.py` — token_usage_log 통계 스크립트
- `c:\tmp\poc_stats\extract_chat_stats.py` — chat_log_new 통계 스크립트
- `c:\tmp\poc_stats\usage_stats.json`, `chat_stats.json` — 본 문서 표 원본 데이터
