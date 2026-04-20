import type { Agent } from "./types";

const CURRENT_USER_ID = "22070101";

export const MOCK_AGENTS: Agent[] = [
  {
    id: "1",
    slug: "sangkwon-analysis",
    name: "상권분석 에이전트",
    description: "입지 분석 및 상권 데이터 기반 인사이트 제공",
    fullDescription: `## 이 에이전트는 무엇인가요?

상권 데이터 API를 기반으로 입지 분석 및 비즈니스 인사이트를 대화형으로 제공합니다.
영업·기획 단계에서 "여기 상권 어때?"라는 질문에 즉시 답변을 받을 수 있습니다.

## 주요 기능

- 지역별 상권 분석 리포트 생성
- 경쟁 업체 분석
- 유동 인구 데이터 분석
- 매출 예측 모델링

## 사용 예시

> "강남역 인근 카페 창업 가능성 분석해줘"
> "판교 테크노밸리 유동인구 트렌드 보여줘"

## 참고

- 공공데이터포털 상권분석 API 기반
- 응답 소요: 보통 30초 내외`,
    capabilities: ["chat"],
    status: "active",
    visibility: "public",
    author: { name: "홍길동", userId: "22010101", department: "경영기획팀" },
    platform: "MISO Agent",
    version: "1.2.0",
    installCount: 156,
    icon: "MapPin",
    tags: ["상권", "입지", "분석"],
    parameters: [],
    executionHistory: [
      { id: "1", timestamp: "2026-04-15 14:32", user: "김철수", status: "success", duration: "28초" },
      { id: "2", timestamp: "2026-04-15 11:20", user: "박영희", status: "success", duration: "35초" },
      { id: "3", timestamp: "2026-04-14 16:45", user: "이민수", status: "failed" },
    ],
    isInstalled: true,
    isMine: false,
  },
  {
    id: "2",
    slug: "qcost-weekly-report",
    name: "Q-cost 주간 리포트",
    description: "품질 비용 데이터를 자동 집계하여 주간 리포트 생성",
    fullDescription: `## 이 에이전트는 무엇인가요?

매주 월요일 아침 자동으로 지난주 품질 비용(Q-cost)을 집계하여 리포트로 전달합니다.
수동 집계에 걸리던 2시간을 0으로 줄입니다.

## 자동화 프로세스

1. ERP 시스템에서 품질 관련 비용 데이터 추출
2. 데이터 정제 및 분류
3. 주간 트렌드 분석
4. Excel/PDF 리포트 문서 생성
5. 관련 부서 자동 배포

## 산출물

- Excel 상세 데이터 (\`qcost_2026W15.xlsx\`)
- PDF 요약 리포트 (3페이지)
- 대시보드 자동 업데이트

## 실행 방식

- **스케줄**: 매주 월 09:00 자동 실행
- **수동 실행**: 채팅에서 "Q-cost 리포트 뽑아줘" 요청 가능
- 실행 후 결과까지 보통 5~7분 소요`,
    capabilities: ["run", "scheduled", "async"],
    status: "active",
    visibility: "team",
    author: { name: "김영희", userId: "22020202", department: "품질팀" },
    platform: "MISO Workflow",
    version: "2.0.1",
    installCount: 34,
    estimatedDurationSec: 420,
    icon: "FileBarChart",
    tags: ["품질", "리포트", "주간"],
    executionHistory: [
      { id: "1", timestamp: "2026-04-13 09:00", user: "시스템", status: "success", duration: "5분 12초" },
      { id: "2", timestamp: "2026-04-06 09:00", user: "시스템", status: "success", duration: "4분 58초" },
    ],
    isInstalled: true,
    isMine: false,
  },
  {
    id: "3",
    slug: "kifrs-guide",
    name: "K-IFRS 회계기준 가이드",
    description: "K-IFRS 회계 기준에 대한 질의응답 지식베이스",
    fullDescription: `## 이 에이전트는 무엇인가요?

한국채택국제회계기준(K-IFRS) 전문 문서와 내부 회계정책을 RAG로 검색하여 답변합니다.
"이런 케이스 어느 기준에 해당돼?" 같은 실무 질문에 출처 링크와 함께 답변합니다.

## 포함 내용

- K-IFRS 전문 기준서 (1001호 ~ 1116호)
- 해석서 및 적용사례
- 내부 회계 정책 문서
- FAQ 및 실무 가이드

## 사용 예시

> "리스 계약을 자산으로 인식할 때 기준 조항 알려줘"
> "재고자산 평가 손실 회계처리 방법은?"

답변에는 **출처 기준서 조항 링크**가 함께 제공됩니다.`,
    capabilities: ["chat"],
    status: "active",
    visibility: "public",
    author: { name: "정회계", userId: "22030303", department: "재무팀" },
    platform: "Workspace (RAG)",
    version: "1.5.3",
    installCount: 412,
    icon: "BookOpen",
    tags: ["회계", "K-IFRS", "규정", "RAG"],
    executionHistory: [
      { id: "1", timestamp: "2026-04-15 15:20", user: "정회계", status: "success", duration: "1초" },
      { id: "2", timestamp: "2026-04-15 14:10", user: "김재무", status: "success", duration: "2초" },
    ],
    isInstalled: true,
    isMine: false,
  },
  {
    id: "4",
    slug: "tax-invoice-issue",
    name: "매입 세금계산서 발행",
    description: "거래처 정보 기반 매입 세금계산서 자동 발행 (홈택스)",
    fullDescription: `## 이 에이전트는 무엇인가요?

거래처/금액/세금유형만 주면 PAD가 홈택스에 로그인해 세금계산서를 자동 발행합니다.
건당 30초~1분 소요되며, 완료되면 발행 결과를 채팅방으로 알려드립니다.

## 프로세스

1. 거래처 정보 검증
2. 매입 데이터 확인
3. 세금계산서 생성
4. 홈택스 자동 로그인 → 전자 발행
5. SAP ERP 전표 자동 생성

## 사용 시 유의

- 발행 후 취소는 홈택스에서 직접 처리 필요
- 거래처 코드가 마스터에 없으면 발행 실패
- 한 번에 최대 50건까지 batch 처리`,
    capabilities: ["run", "async"],
    status: "active",
    visibility: "team",
    author: { name: "박회계", userId: "22040404", department: "재무팀" },
    platform: "PAD (EC2 Runner)",
    version: "1.0.0",
    installCount: 22,
    estimatedDurationSec: 180,
    icon: "Receipt",
    tags: ["세금계산서", "매입", "홈택스", "PAD"],
    parameters: [
      { name: "vendorCode", type: "string", description: "거래처 코드", required: true },
      { name: "amount", type: "number", description: "금액", required: true },
      { name: "taxType", type: "string", description: "세금 유형", required: true },
    ],
    executionHistory: [
      { id: "1", timestamp: "2026-04-15 16:00", user: "박회계", status: "running" },
      { id: "2", timestamp: "2026-04-15 14:30", user: "김재무", status: "success", duration: "2분 30초" },
    ],
    isInstalled: false,
    isMine: false,
  },
  {
    id: "5",
    slug: "sap-cost-extract",
    name: "SAP 원가 데이터 추출",
    description: "SAP CO 모듈에서 원가 데이터를 추출하는 파이썬 매크로",
    fullDescription: `## 이 에이전트는 무엇인가요?

SAP CO(Controlling) 모듈에서 원가 데이터를 대량 추출해 분석용 데이터셋으로 만들어줍니다.
실행 시간은 데이터량에 따라 10분~30분 정도 걸립니다.

## 추출 데이터

- 제조원가 명세
- 원가센터별 비용
- 프로젝트별 원가
- 제품별 표준원가

## 현재 상태

⚠️ 시스템 점검으로 일시 중단 중입니다. 점검 예상 완료: 2026-04-20`,
    capabilities: ["run", "async"],
    status: "maintenance",
    visibility: "public",
    author: { name: "이구매", userId: "22050505", department: "구매팀" },
    platform: "Python (EC2 Runner)",
    version: "2.3.0",
    installCount: 78,
    estimatedDurationSec: 900,
    icon: "Database",
    tags: ["SAP", "원가", "ERP", "Python"],
    executionHistory: [
      { id: "1", timestamp: "2026-04-10 10:00", user: "이구매", status: "success", duration: "15분" },
    ],
    isInstalled: false,
    isMine: false,
  },
  {
    id: "6",
    slug: "recruit-faq",
    name: "채용 FAQ 봇",
    description: "채용 관련 자주 묻는 질문에 자동 응답",
    fullDescription: `## 이 에이전트는 무엇인가요?

채용 프로세스 및 복리후생 관련 질문에 24시간 답변합니다.
지원자가 인사팀에 직접 문의하지 않아도 대부분의 질문이 즉시 해결됩니다.

## 응답 가능 주제

- 채용 절차 안내
- 지원서 작성 가이드
- 면접 준비 팁
- 복리후생 정보
- 근무 환경 안내

## 특징

- 한국어/영어 동시 응답
- 답변 불확실 시 채용 담당자 연결 유도`,
    capabilities: ["chat"],
    status: "active",
    visibility: "public",
    author: { name: "이인사", userId: "22060606", department: "인사팀" },
    platform: "Native (Lucid Worker)",
    version: "1.1.0",
    installCount: 289,
    icon: "MessageCircle",
    tags: ["채용", "FAQ", "인사"],
    executionHistory: [
      { id: "1", timestamp: "2026-04-15 17:30", user: "지원자A", status: "success", duration: "5초" },
      { id: "2", timestamp: "2026-04-15 16:45", user: "지원자B", status: "success", duration: "3초" },
    ],
    isInstalled: false,
    isMine: false,
  },
  {
    id: "7",
    slug: "safety-training-status",
    name: "안전교육 이수현황",
    description: "임직원 안전교육 이수 현황 조회 및 미이수자 알림",
    fullDescription: `## 이 에이전트는 무엇인가요?

안전교육 이수 데이터를 스캔하여 부서별 이수율 리포트를 생성하고,
법정 필수 교육 미이수자에게 자동 알림을 발송합니다.

## 기능

- 개인별 교육 이수 현황 조회
- 부서별 이수율 통계
- 미이수자 메일 알림 발송
- 법정 필수 교육 관리

## 상태

⛔ 시스템 개편으로 현재 비활성 상태입니다.`,
    capabilities: ["run", "scheduled", "async"],
    status: "inactive",
    visibility: "team",
    author: { name: "박안전", userId: "22070707", department: "안전환경팀" },
    platform: "n8n Workflow",
    version: "0.9.0",
    installCount: 12,
    estimatedDurationSec: 300,
    icon: "Shield",
    tags: ["안전", "교육", "법정", "n8n"],
    executionHistory: [],
    isInstalled: false,
    isMine: false,
  },
  {
    id: "8",
    slug: "fx-analysis",
    name: "외화자금 분석",
    description: "외화 자금 흐름 분석 및 환율 리스크 관리 에이전트",
    fullDescription: `## 이 에이전트는 무엇인가요?

실시간 환율 API와 내부 외화 포지션 데이터를 결합해 환율 리스크를 분석합니다.
재무팀의 일일 환율 모니터링 업무를 자연어 대화로 대체합니다.

## 주요 기능

- 실시간 환율 모니터링
- 외화 포지션 분석
- 헷징 전략 추천
- 환손익 시뮬레이션

## 지원 통화

USD, EUR, JPY, CNY, GBP 등 주요 20개 통화

## 사용 예시

> "달러 환율 이번 주 흐름 요약"
> "엔화 헷지 포지션 리스크 분석"`,
    capabilities: ["chat"],
    status: "active",
    visibility: "public",
    author: { name: "김재무", userId: "22080808", department: "재무팀" },
    platform: "MISO Agent",
    version: "1.3.2",
    installCount: 94,
    icon: "TrendingUp",
    tags: ["외화", "환율", "재무"],
    parameters: [],
    executionHistory: [
      { id: "1", timestamp: "2026-04-15 17:00", user: "김재무", status: "success", duration: "10초" },
      { id: "2", timestamp: "2026-04-15 09:30", user: "박외환", status: "success", duration: "8초" },
    ],
    isInstalled: true,
    isMine: false,
  },
  {
    id: "9",
    slug: "my-schedule-summary",
    name: "내 업무 일정 요약",
    description: "(개발 중) 개인 일정을 주간 단위로 요약",
    fullDescription: `## 이 에이전트는 무엇인가요?

캘린더 연동을 통해 개인 주간 업무 일정을 자동 요약합니다.

## 상태

- Private 범위로 개인 테스트 중
- 일반 공개 전 동료 피드백 수집 예정`,
    capabilities: ["chat"],
    status: "active",
    visibility: "private",
    author: { name: "나", userId: CURRENT_USER_ID, department: "개발팀" },
    platform: "Native (Lucid Worker)",
    version: "0.1.0",
    installCount: 1,
    icon: "Sparkles",
    tags: ["일정", "요약", "개인"],
    executionHistory: [],
    isInstalled: true,
    isMine: true,
  },
  {
    id: "10",
    slug: "newsletter-archiver",
    name: "뉴스레터 아카이버",
    description: "(개발 중) 수신된 뉴스레터 메일을 Wiki에 자동 아카이빙",
    fullDescription: `## 이 에이전트는 무엇인가요?

부서 메일함에 수신되는 뉴스레터를 AI로 요약해서 Wiki에 자동 저장합니다.

## 프로세스

1. 메일함 내 뉴스레터 폴더 모니터링
2. AI 요약 생성
3. L&F WIKI 부서 컬렉션에 업로드

## 상태

- 매일 08:00 자동 실행
- 개인 Private 상태 (기능 검증 중)`,
    capabilities: ["run", "scheduled", "async"],
    status: "active",
    visibility: "private",
    author: { name: "나", userId: CURRENT_USER_ID, department: "개발팀" },
    platform: "n8n Workflow",
    version: "0.2.0",
    installCount: 1,
    estimatedDurationSec: 120,
    icon: "Newspaper",
    tags: ["메일", "Wiki", "아카이빙", "n8n"],
    executionHistory: [
      { id: "1", timestamp: "2026-04-15 08:00", user: "시스템", status: "success", duration: "45초" },
    ],
    isInstalled: true,
    isMine: true,
  },
];

export const DEPARTMENTS = [
  "전체",
  "경영기획팀",
  "품질팀",
  "재무팀",
  "구매팀",
  "인사팀",
  "안전환경팀",
  "개발팀",
];
