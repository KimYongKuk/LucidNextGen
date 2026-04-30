"""도메인-워커 라우팅 가이드 (Single Source of Truth)

IntentClassifier(Haiku, 단일 인텐트 분류)와 Planner(Sonnet, Task DAG 분해)는
서로 다른 LLM·다른 출력 형식을 사용하지만, **도메인 → 워커 매핑은 동일**해야 한다.

이 모듈은 두 분류기가 공통으로 사용하는 도메인 라우팅 가이드 텍스트를 단일 정의한다.
- intent_classifier.py: CLASSIFIER_PROMPT의 `{domain_routing_guide}` 슬롯에 주입
- planner.py: PLANNER_SYSTEM의 `{domain_routing_guide}` 슬롯에 주입

라우팅 룰을 추가/변경할 때는 이 파일만 수정하면 두 분류기에 자동 반영된다.

배경 (2026-04-29 → 2026-04-30):
- 4/29: "정보보안 관리 규정"/"경비처리 규정"이 corp_rag로 잘못 분류되던 결함을
  intent_classifier.py에만 수정 → 운영의 11% Planner 경로에서 결함 잔존
- 4/30: 동일 결함이 Planner-Executor 경로에서 재발("법인카드 사용 규정")
  → 두 프롬프트에 도메인 가드를 중복 유지하던 구조의 비효율 노출
- 해결: 도메인 매핑·배타성 원칙을 본 모듈로 추출하여 단일 진실 원천화
"""


DOMAIN_ROUTING_GUIDE = """## 도메인 → 워커 매핑

| 도메인 | 키워드 (예시) | 워커 |
|--------|---------------|------|
| 회계/재경 | 법인카드, 결산, 세금계산서, SAP 전표, 경비, 예산, 자산, 부가세, 원천징수, 적격증빙, 접대비, 자금, 매출, 매입 | `acct_support` |
| IT/보안 | VPN, 쉐도우큐브, AD, SAP GUI, Citrix, 비밀번호, OTP, 메일용량, DRM, DLP, 방화벽, 백신, 매체제어, LFON | `it_support` |
| HR/인사 | 인사, 급여, 복리후생, 휴가, 경조, 채용, 직급, 평가, 교육 | `corp_rag` |
| 안전·환경 | 안전관리, 환경, 보건, 화학물질, 비상대응 | `corp_rag` |
| 결재함/양식 | 결재 대기, 기안함, 전표품의, 품의서, 사전지출 승인서 | `approval` |
| 메일함 | 받은편지함, 보낸메일, 안 읽은 메일, 메일 본문 | `mail` |
| 사내 게시판 | 공지사항, 게시글, 사내 공지 | `board` |
| L&F Wiki | 위키, outline, 위키 문서, 위키 컬렉션 | `outline` |
| 회의실/예약 | 회의실, 빈 회의실, 예약 등록/취소 | `reservation` |
| 캘린더 | 일정, 캘린더, 스케줄, 빈 시간 | `calendar` |
| NAS | NAS, 공유 폴더, 부서간 공유, 파일 서버 | `nas` |

## 도메인 배타성 원칙 (CRITICAL)

1. **단일 도메인 질의 → 단일 워커**: 도메인 워커(`acct_support`, `it_support`, `corp_rag`, `approval`, `mail`, `board`, `outline`)는 서로 배타적입니다. 회계 도메인 질의에 `corp_rag`를 헤지로 추가하지 마세요.

2. **"규정/정책/지침"은 도메인 신호가 아닙니다**: 함께 등장하는 명사로 도메인을 결정하세요.
   - "법인카드 사용 **규정**" → 회계 (`acct_support`) — `corp_rag` 추가 금지
   - "VPN 사용 **정책**" → IT (`it_support`)
   - "경조 휴가 **규정**" → HR (`corp_rag`)
   - "안전관리 **지침**" → 안전 (`corp_rag`)

3. **워커별 보유 docs**:
   - `corp_rag` → HR docs(인사·복리후생·휴가) + 안전·환경 docs **만**
   - `acct_support` → 회계·재경 docs + 회계 VOC 사례
   - `it_support` → IT·보안 docs + IT VOC 사례 + 계정/패스워드 운영
   회계·IT 질의에 `corp_rag`를 추가하면 `search_hr_docs`가 무관한 인사팀 문서를 끌어와 응답 품질을 떨어뜨립니다.

4. **도메인 모호 시 우선순위**:
   - "결산" (settlement) → `acct_support` (NOT approval)
   - "WA전표품의" 등 양식명 → `approval` (NOT acct_support)
   - "전자결재 게시글" → `board` (action=게시글 검색)
   - "결재 반려 메일" → `mail` (action=메일 검색)
"""
