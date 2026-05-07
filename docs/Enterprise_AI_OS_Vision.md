# Enterprise AI OS — L&F의 통합 AI 운영체계 비전

> 작성일: 2026-05-07
> 작성자: 김용국 (DA Part Leader)
> 상태: v0.1 초안 (C레벨 보고 사전 자료)
> 관련 문서:
> - `docs/AI_허브_통합_설계_초안.md` — Layer 1/2 하위 설계 (서비스 허브)
> - `docs/ARCHITECTURE.md` — Lucid 시스템 아키텍처 (현행)
> - `docs/Outline_Wiki_연계_설계안.md` — Layer 3 (Knowledge Layer) 하위 설계

---

## 0. 한 줄 비전

> **L&F는 이미 보유한 제조 데이터 인프라 위에, 자연어로 호출되는 통합 AI 운영체계(Enterprise AI OS)를 구축한다.**
> 이는 Lucid Hub(전사 진입점) + MISO Builder(에이전트 제작) + Knowledge Layer(지식) + Operations Layer(제조 통합)의 **4-Layer 아키텍처**로 구현되며, DA Part가 그 통합 책임을 가진다.

---

## 1. Executive Summary

### 1.1 무엇을 하는가
- L&F가 이미 보유한 **MDM, 설비 태그/Historian, SCADA, QMS, CMMS, 디지털트윈**을 단일한 자연어 운영체계 위에서 활용
- 이미 운영 중인 **Lucid (500+ 사용자, 월 10,000+ 쿼리)** 와 **MISO PoC** 결과를 단일 플랫폼으로 통합
- 글로벌 제조업 평균 수준의 AI 인력(전사 1%, 16~22명)을 단계적으로 확보

### 1.2 왜 지금인가
- L&F는 이미 **ISA-95 4단계 통합에 근접한 운영 인프라**를 보유 — 글로벌 양극재 제조업에서도 흔치 않은 자산
- **Palantir Foundry가 비싸게 파는 Operational Ontology를 자체 구축한 셈** — 이 위에 Intelligence Layer를 얹기만 하면 됨
- 경쟁사(CATL, 국내 양극재 3사)의 AI 도입 가속화 → 1~2년 내 도입 못하면 글로벌 레퍼런스 자리를 빼앗김

### 1.3 핵심 숫자 3개 (PoC + 운영 실적 기반)
| 지표 | 현재 | Phase 1 목표 (6개월) | Phase 3 목표 (3년) |
|------|------|----------------------|---------------------|
| Lucid 월간 활성 사용자 | TBD (~500) | 1,000+ | 1,500+ |
| 자동화/AI 도구 사용 사례 | ~10개 | 30개+ | 100개+ |
| Operations Layer 연동 시스템 | 0개 | 1~2개 (PoC) | 5개+ (정상 운영) |

> ※ 정확한 수치는 PoC 보고 직전 최종 확정.

### 1.4 의사결정 요청 (3건)
1. **Industrial Intelligence Layer 책임 권한**을 DA Part에 부여
2. **Phase 1 인력 충원** 승인 (현 N명 → 8~10명, 코어팀 구성)
3. **Operations Layer Gateway 표준화 권한** — 제조 데이터옵스 부서와 공동 거버넌스 위원회 구성

---

## 2. 배경: L&F가 이미 보유한 자산의 재인식

### 2.1 자산 현황

| 자산 | 보유 여부 | 의미 |
|------|-----------|------|
| MDM (자재/설비/BOM 마스터) | O | 단순 RDBMS가 아닌, **거버넌스가 적용된 마스터 데이터** |
| 설비 태그 마스터 + Historian | O | 시계열 데이터에 **정규 태그 체계** 존재 |
| SCADA | O | 실시간 공정 운영 데이터 수집 채널 확보 |
| QMS | O | 품질 검사·부적합·CAPA·SPC 통합 |
| CMMS | O | 정비 이력·작업지시·예방정비 체계화 |
| 디지털트윈 | O | 위 데이터가 **3D/논리 모델 위에 매핑** — 엔티티 모델링 완료의 강력한 신호 |

### 2.2 의미

> 이는 사실상 **ISA-95 Level 4 통합 모델에 근접**한 상태이며, 글로벌 제조업 기준으로도 흔치 않다.
>
> **Palantir Foundry / AIP가 솔루션 비용 수십억~수백억 원으로 판매하는 "Operational Ontology"를 L&F는 자체 구축하여 보유 중이다.**

이 사실을 임원진이 다시 한 번 인지하는 것이 본 비전의 출발점이다. 기존 추진 부서/외부 컨소시엄의 노력이 만든 이 인프라가 없었다면, 이 비전 자체가 성립하지 않는다.

### 2.3 빠진 조각: Intelligence Layer

운영 데이터 인프라(Foundation)는 있지만, 그 위에서 **자연어로 의사결정을 돕는 Intelligence Layer**가 비어 있다.

- 현장: 데이터를 보러 시스템 5~6개를 옮겨다님
- 분석: 매번 SQL/엑셀 작업 반복
- 의사결정: 통합 시야 부재

→ Enterprise AI OS는 이 빈 자리를 채운다.

---

## 3. 4-Layer Architecture

### 3.1 전체 구조

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 1: Lucid Hub                                           │
│  ─ 전사 단일 진입점 (Web / Mobile / 위젯)                       │
│  ─ 사용자 UX, 권한·SSO, 대화 이력, 사용 추적                     │
│  ─ Orchestrator → Worker 분기 → MCP Tool 호출                  │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: MISO Builder                                        │
│  ─ 에이전트/워크플로우 제작 플랫폼 (Citizen Developer)           │
│  ─ Lucid Hub에 등록되어 자연어로 호출됨                          │
│  ─ 부서별 자체 자동화 → DA Part 검토 → Hub 배포                  │
├──────────────────────────────────────────────────────────────┤
│  Layer 3: Knowledge Layer                                     │
│  ─ 위키, 문서, DB 스키마, 규정, SOP                              │
│  ─ 정적·반정적 지식 (RAG 기반: ChromaDB + BGE-M3)                │
│  ─ Outline Wiki 연계, 사내 문서 자동 동기화                      │
├──────────────────────────────────────────────────────────────┤
│  Layer 4: Operations Layer                                    │
│  ─ MDM / SCADA / QMS / CMMS / Historian / 디지털트윈            │
│  ─ 실시간·이벤트성 운영 데이터                                   │
│  ─ Operations Layer Gateway 통한 표준화된 접근만 허용            │
└──────────────────────────────────────────────────────────────┘
         ↑ Knowledge Card Pipeline (Ops → Knowledge 카드 변환)
         ↓ MCP Gateway (Hub/Builder → Ops 도구 호출, Tier별 거버넌스)
```

### 3.2 Layer 1: Lucid Hub

**책임**: 전사 임직원의 AI 단일 진입점.

| 항목 | 내용 |
|------|------|
| 사용자 UI | Web (Next.js), 모바일 PWA, 위젯, IDE/VSCode 확장 (단계적) |
| 인증 | SSO (AD/LDAP), 권한 그룹 매핑 |
| 핵심 기능 | 자연어 채팅, 워크스페이스, 문서 업로드/검색, PDF·차트 생성, YouTube 요약, 메일 조회, 캘린더 |
| 거버넌스 | 사용 로그 전수 수집, 부적절 사용 모니터링, A/B 실험 |
| 운영 책임 | DA Part |

**현 상태**: 운영 중. 본 비전에서는 **확장과 표준화의 베이스**.

### 3.3 Layer 2: MISO Builder

**책임**: 코드 없이 또는 적은 코드로 부서가 직접 에이전트/자동화를 만드는 플랫폼.

| 항목 | 내용 |
|------|------|
| 빌더 형태 | n8n 유사 워크플로우 + LLM Agent 노드 (MISO PoC 기반) |
| 등록/배포 | Service Registry → Lucid Hub의 ExternalAgentWorker가 자동 호출 |
| 검증 단계 | DA Part 사전 검토 → Tier에 따라 자동/승인 분기 |
| 사용자 | Citizen Developer (현업 분석가, RPA 담당자, IT 담당자) |
| 운영 책임 | DA Part 플랫폼 운영 + 각 부서 콘텐츠 책임 |

**관련 하위 설계**: `docs/AI_허브_통합_설계_초안.md`

### 3.4 Layer 3: Knowledge Layer

**책임**: 정적·반정적 지식의 단일 소스.

| 항목 | 내용 |
|------|------|
| 소스 | Outline Wiki, 사내 SOP/규정/매뉴얼, DB 스키마 카탈로그, IT/회계 VOC |
| 저장 | ChromaDB (벡터) + MySQL (메타) |
| 임베딩 | BGE-M3 (다국어, 한국어 강함) |
| 갱신 | 위키 변경 이벤트 → 자동 재인덱싱 / 야간 배치 |
| 거버넌스 | 출처 추적 필수, "환각 시 책임" 정의, 민감도 라벨링 |

**관련 하위 설계**: `docs/Outline_Wiki_연계_설계안.md`

### 3.5 Layer 4: Operations Layer

**책임**: 실시간·이벤트성 운영 시스템과의 통합 — 가장 민감하고 위험한 레이어.

| 시스템 | 데이터 성격 | 사용 패턴 (1차) | 위험도 |
|--------|-------------|-----------------|--------|
| MDM | 자재/설비/BOM 마스터 | 조회 (Tier 1) | 낮음 |
| Historian | 시계열 태그 | 조회·집계 (Tier 1) | 낮음 |
| SCADA | 실시간 공정 | 조회 (Tier 1), 알람 (Tier 2) | 중 |
| QMS | 검사·부적합 | 조회 (Tier 1), 분석 (Tier 2) | 중 |
| CMMS | WO/정비 이력 | 조회 (Tier 1), WO 생성 (Tier 3) | 높음 |
| 디지털트윈 | 통합 모델 | 조회·시뮬레이션 (Tier 1/2) | 중 |

**핵심 제약**:
- 직접 SQL/API 호출 금지
- **Operations Layer Gateway**(다음 절)를 거친 표준 MCP 도구로만 접근
- 모든 호출에 사용자 ID, 사번, 부서, 호출 사유, Tier 라벨 부착 → 감사 로그

---

## 4. 핵심 원칙

### 4.1 원칙 1: Knowledge vs Operations 분리

| 구분 | Knowledge | Operations |
|------|-----------|------------|
| 데이터 성격 | 정적/반정적 | 실시간/이벤트 |
| 갱신 주기 | 일/주 | 초/분 |
| 위험도 | 낮음 (잘못 답해도 사고 X) | 높음 (잘못 호출 시 라인 정지 가능) |
| 기술 | RAG, 벡터 검색 | 표준 API, 시계열 쿼리, 트랜잭션 |
| 거버넌스 책임 | DA Part + 지식 소유 부서 | DA Part + 운영기술 부서 (공동) |

→ 기술 스택, 거버넌스 모델, SLA를 **반드시 분리**한다.

### 4.2 원칙 2: Operations Layer Gateway = DA Part가 표준 보유

> **이 게이트웨이의 표준 사양과 운영 권한이 DA Part의 핵심 자산이다.**

**역할**:
1. 운영 시스템과 Hub/Builder 사이의 단일 진입 표준
2. 모든 도구 호출에 인증·권한·감사·Tier·Rate Limit 자동 적용
3. 운영 시스템의 내부 변경(스키마, 인증 등)을 외부에 노출되지 않게 흡수

**도구 표준 시그니처 (예시)**:
```python
@mcp_tool(
    name="get_equipment_status",
    tier=Tier.READ_ONLY,
    domain="manufacturing",
    owner="ops_layer_gateway",
    sla_p99_ms=500,
)
def get_equipment_status(
    equipment_id: str,           # Entity Resolution Service로 정규화됨
    time_range: TimeRange,
    requester: RequesterContext, # 사번, 부서, 호출 이유 (LLM 자동 채움)
) -> EquipmentStatus: ...
```

**거버넌스**: 도구 추가/변경은 DA Part 검토 + 데이터 소유 부서 동의 필요.

### 4.3 원칙 3: Entity Resolution Service (MDM 위에 얹기)

LLM이 인간 표현("코팅기 1호")을 시스템 ID("EQ-1234")로 정규화하는 공용 서비스.

```
"양극재 라인 1번의 코팅기"
        ↓
[Entity Resolution Service]
  - MDM 마스터 매칭
  - 별칭 사전 (사내 통용 명칭)
  - 컨텍스트 기반 disambiguation
        ↓
{ entity_type: "equipment", id: "EQ-1234", confidence: 0.94 }
```

→ 모든 Operations 도구가 이 서비스를 거쳐 ID 정규화. **중복 구현 방지, 명칭 변경 시 단일 지점만 수정.**

### 4.4 원칙 4: Knowledge Card Pipeline (Ops → Knowledge)

운영 데이터를 자연어 카드로 변환해 Knowledge Layer에 주입하는 파이프라인.

**예시**:
```
[QMS 부적합 1건 발생]
     ↓
[Card Generator]
"2026-05-06 04:23, 라인 1 코팅기 EQ-1234에서 코팅 두께 부적합 발생.
원인: 슬러리 점도 이상. 조치: SOP-Q-031에 따라 라인 정지 후 재가동.
관련 WO: WO-2026-0512."
     ↓
[Knowledge Layer 인덱싱]
     ↓
나중에 누가 "최근 코팅기 부적합 사례" 질문 시 RAG로 답변 가능
```

**효과**: 운영 데이터의 시간성을 끊어 **지식화** → Tier 1 (읽기) 부담을 줄이고, RAG로 흡수.

### 4.5 원칙 5: Risk Tier별 거버넌스

| Tier | 정의 | 예시 | Citizen Dev | DA 검토 | 별도 승인 |
|------|------|------|:-----------:|:--------:|:---------:|
| Tier 1 | 읽기 전용 조회 | 설비 상태 조회, 어제 부적합 건수 | ✅ 자유 | 가이드만 | — |
| Tier 2 | 분석/진단 | SPC 이상 패턴 탐지, 불량 원인 후보 추론 | ⚠️ 제한 | ✅ 필수 | — |
| Tier 3 | 실행/제어 | WO 자동 생성, 알람 발송, 외부 메일 발송, SAP 트랜잭션 | ❌ 금지 | ✅ 필수 | ✅ 운영기술 부서 공동 책임 |

**원칙**:
- 기본값은 가장 낮은 Tier
- Tier 상승은 단방향 승인 프로세스
- Tier 3 도구는 **드라이런 모드** 필수 (실제 실행 전 결과 미리보기)

---

## 5. 거버넌스 모델

### 5.1 DA Part의 포지션: Industrial Intelligence Layer Owner

> 제조 데이터옵스(기존 추진 부서) = **기반(Foundation)**
> DA Part = **그 위에 얹는 Intelligence Layer**

**핵심 원칙**:
- 이미 구축된 운영 데이터 인프라 영역에 들어가서 **재설계 제안 금지**
- "여러분의 인프라가 있어서 가능한 일"이라는 프레이밍 일관 유지
- 기존 부서/외부 컨소시엄을 **협력자**로 명시

### 5.2 협력 거버넌스 구조

```
┌─────────────────────────────────────────────┐
│         AI 운영 위원회 (분기 1회)              │
│  ─ CIO/CTO/CDO + DA Part Leader              │
│  ─ 제조 데이터옵스 부서장 + 운영기술 부서장    │
│  ─ 정보보안 책임자                            │
└─────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────┐
│       Operations Gateway 워킹그룹 (월 1회)    │
│  ─ DA Part (표준 소유)                        │
│  ─ 제조 데이터옵스 / 운영기술 (도메인)         │
│  ─ 도구 추가/변경 합의                         │
└─────────────────────────────────────────────┘
```

### 5.3 AI Champion 네트워크 (Hub-and-Spoke)

각 현업 부서에 1~2명의 AI Champion을 임베드한다.

| 부서 | Champion 역할 |
|------|---------------|
| 품질 | QMS/SPC 도구 후보 발굴, 사용자 피드백 |
| 생산기술 | SCADA/Historian 도구, 공정 인사이트 |
| 정비 | CMMS/WO 자동화, 설비 이상 진단 |
| 경영지원 | 메일/캘린더/문서 자동화 |
| IT | 사내 운영 자동화, RPA 연계 |

- **소속**: 현업 부서 정규 인력
- **점선 보고**: DA Part
- **효과**: 풀타임 AI 인건비를 코어팀(DA Part)에만 집중하면서 실질 관여 인력은 30~40명 확보 → 정치적 공격 분산

---

## 6. 유스케이스 시나리오 (Phase 1 후보)

> ※ Phase 1 PoC 우선순위는 임원 보고 후 운영기술/품질/정비 부서장과 협의해 확정.

### UC1: (예시) 품질 부적합 자연어 진단

**현재**: 부적합 발생 → QMS 조회 → SPC 차트 확인 → 정비 이력(CMMS) 조회 → 자재 로트(MDM) 추적 → 사람이 종합 판단 (시스템 5개, 30분~수 시간)

**After**:
> "어제 라인 1 코팅 부적합 건들 중 EQ-1234 관련만 추려서, 같은 시간대 슬러리 로트와 정비 이력 같이 보여줘"
>
> → **Phase 1: 카드 형태 보고서 자동 생성 (Tier 1, 5초)**

**필요 도구 (Operations Gateway)**:
- `qms.search_nonconformance` (Tier 1)
- `historian.get_tag_history` (Tier 1)
- `cmms.get_equipment_wo_history` (Tier 1)
- `mdm.trace_material_lot` (Tier 1)

**Tier**: 모두 Tier 1 (읽기 전용) → Citizen Dev 자유 사용 가능 영역

### UC2: (예시) 정비 작업지시 초안 자동 생성

**현재**: 설비 이상 발생 → 정비사가 CMMS에서 WO 직접 작성 → 표현 차이로 검색 누락 빈번

**After**:
> "EQ-1234 코팅 두께 산포 증가 보이는데, 비슷한 과거 사례 있으면 그 조치 사항 기반으로 WO 초안 작성해줘"
>
> → **Phase 2: 과거 WO RAG (Knowledge) + 최근 24h 데이터(Operations) → WO 초안 (Tier 3, 드라이런 → 정비사 승인 후 등록)**

### UC3: (현행 확장) 사내 RAG 챗봇

이미 운영 중인 Lucid의 CorpRAG 기능 — Outline Wiki 연계, 부서별 권한 적용 강화.

> ※ 추가 유스케이스는 부록 또는 별도 문서로.

---

## 7. 로드맵

### Phase 1 — 기반 구축 (~6개월)

| 항목 | 목표 |
|------|------|
| 인력 | 8~10명 (현 N명 → +X) |
| 거버넌스 | AI 운영 위원회 발족, Tier 정책 합의 |
| Layer 1/2/3 | 현 운영 안정화 + Outline 연계 완료 |
| Layer 4 | Operations Gateway v0.1 + Tier 1 도구 5~10개 |
| 유스케이스 | Tier 1 PoC 1~2건 (품질/생산기술 우선) |

### Phase 2 — Operations 확장 (6~18개월)

| 항목 | 목표 |
|------|------|
| 인력 | 14~16명 |
| Layer 4 | Tier 1 도구 20개+, Tier 2 도구 도입 시작 |
| 유스케이스 | 부서별 안정 운영 5~10건 |
| Knowledge Card Pipeline | QMS/CMMS 자동 카드화 운영 |
| 디지털트윈 연동 | 시뮬레이션 도구 PoC |

### Phase 3 — 풀 4-Layer 안정 운영 (18~36개월)

| 항목 | 목표 |
|------|------|
| 인력 | 18~22명 (전사 1%) |
| 모든 레이어 정상 운영, Tier 3 안정 도입 |
| 외부 사례화: 컨퍼런스 발표, 벤더 파트너십 |
| 양극재 도메인 글로벌 레퍼런스 확보 |

---

## 8. 조직 모델

### 8.1 인력 구성 (Phase 3 최종 22명 기준)

| 역할 | 인원 | 책임 |
|------|------|------|
| 아키텍트 / 리드 | 1 | 전체 비전 + 외부 가시성 |
| AX 전략 / PM | 1~2 | 부서 대응, 우선순위, 보고 |
| 플랫폼 엔지니어링 | 3 | Lucid Hub, Service Registry |
| 프론트엔드/UX | 2 | Web, PWA, 위젯, 빌더 UI |
| SRE / 인프라 / 보안 | 2 | 배포, 모니터링, 감사 로그 |
| Builder 운영 | 1 | MISO 운영, Citizen Dev 지원/교육 |
| 에이전트 품질 검토 | 1 | 배포 전 검증, Tier 정책 |
| 데이터 엔지니어 (RAG) | 2 | 인덱싱, 임베딩, 카탈로그 |
| 지식 큐레이션 | 1 | Wiki, SOP 정리, 출처 관리 |
| 시스템 통합 (MCP) | 2 | Operations Gateway, 도구 표준 |
| 도메인 분석가 | 2 | 품질/생산/정비 도메인 짝꿍 |
| AI/ML 엔지니어 | 2 | 모델, RAG 품질, 평가 |
| **합계** | **20~22** | — |

### 8.2 점진 확충 경로

- 각 Phase 시작 시 Hiring Plan 갱신
- 단계 진입 조건은 **기술 마일스톤 + 사용 지표 + ROI** 3종 모두 충족 시
- 채용 어려움 대비: **외부 SI 위탁 50% / 내부 정직원 50%** 비율 권장

---

## 9. 외부 레퍼런스

| 레퍼런스 | 시사점 | L&F 적용 |
|----------|--------|----------|
| Palantir Foundry / AIP | Operational Ontology 구축으로 가치 창출 | L&F는 이미 자체 보유, **외부 비용 없이 동등 효과 가능** |
| Microsoft Copilot Stack | Hub + Builder 분리, 거버넌스 강조 | 4-Layer의 Hub/Builder/Knowledge에 직접 매핑 |
| Siemens MindSphere | OT/IT 게이트웨이 모델 | Operations Gateway 사양의 직접 참조 |
| CATL / Tesla Gigafactory AI | 제조 LLM 사례화 진행 중 | 양극재 도메인은 **국내 최초 + 글로벌 초기 진입자** 가능 |
| 국내 양극재 경쟁사 | 일부 RAG 챗봇 도입 단계 | L&F는 Hub 운영 단계 — **1~2년 앞서 있음** |

---

## 10. 리스크와 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 보안 사고 (운영 데이터 노출) | 高 | Operations Gateway 의무화, Tier 정책, 사용자 단위 감사 로그 |
| 운영 사고 (잘못된 실행) | 高 | Tier 3 도구는 드라이런 + 운영기술 부서 공동 승인 |
| 기존 부서와의 마찰 | 中 | "Intelligence Layer" 프레이밍, 협력 위원회 분기 회의 |
| 외부 의존 / 락인 | 中 | Bedrock + 자체 운영(Lucid) 비중 유지, MCP 표준 채택 |
| ROI 불확실성 | 中 | Phase별 사용 지표 + 시간 절감 측정 + 점진 확충 |
| 채용 난이도 | 中 | SI 50% 병행, 내부 전환(SAP→AI 사례), Champion 네트워크 |
| 환각 / 잘못된 답변 | 中 | 출처 표시 의무, 신뢰도 라벨, RAG 우선 (LLM 단독 X) |

---

## 11. 의사결정 요청 (재진술)

### 11.1 권한
**Industrial Intelligence Layer 책임 권한**을 DA Part에 부여
- 4-Layer 비전의 **단일 책임자**
- Operations Gateway 표준 소유
- AI Champion 네트워크 점선 보고 권한

### 11.2 인력
**Phase 1 인력 충원 승인**
- 현 N명 → 8~10명
- 핵심 충원: 시스템 통합(MCP) 2명, 플랫폼 엔지니어 1명, 프론트엔드 1명, 도메인 분석가 1명

### 11.3 거버넌스
**Operations Layer Gateway 표준화 권한 + 공동 거버넌스 위원회 구성**
- DA Part가 게이트웨이 표준을 소유
- 도구 추가는 데이터 소유 부서와 공동 승인
- AI 운영 위원회 분기 1회 임원진 보고

---

## 부록 A. 용어 정의

| 용어 | 정의 |
|------|------|
| Enterprise AI OS | 4-Layer로 구성된 L&F의 통합 AI 운영체계 |
| Lucid Hub | 전사 AI 단일 진입점 (Layer 1) |
| MISO Builder | 에이전트/워크플로우 제작 플랫폼 (Layer 2) |
| Knowledge Layer | 정적·반정적 지식 RAG (Layer 3) |
| Operations Layer | 제조 운영 시스템 통합 (Layer 4) |
| Operations Gateway | Layer 4 접근 표준 + 거버넌스 단일 지점 |
| Entity Resolution Service | "코팅기 1호" → "EQ-1234" 정규화 서비스 |
| Knowledge Card | Operations 데이터를 자연어로 변환한 RAG 단위 |
| Tier 1/2/3 | 읽기 / 분석 / 실행 위험도 분류 |
| AI Champion | 현업 부서 임베드 인력, DA Part에 점선 보고 |
| Hub-and-Spoke | 중앙 코어 + 현업 임베드 조직 모델 |

## 부록 B. 관련 문서

| 문서 | 역할 |
|------|------|
| `docs/AI_허브_통합_설계_초안.md` | Layer 1/2 하위 설계 (서비스 허브) |
| `docs/ARCHITECTURE.md` | Lucid 시스템 아키텍처 (현행) |
| `docs/Outline_Wiki_연계_설계안.md` | Layer 3 (Knowledge Layer) 하위 설계 |
| `docs/RPA_어댑터_초안.md` | Layer 2 외부 연동 설계 |
| `docs/Security_Guard_Agent_설계안.md` | 거버넌스 / Tier 정책 관련 |

## 부록 C. 변경 이력

| 날짜 | 버전 | 변경 |
|------|------|------|
| 2026-05-07 | v0.1 | 초안 작성 (C레벨 보고 사전 자료) |
