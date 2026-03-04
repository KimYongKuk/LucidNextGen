# 서비스 레포트 대시보드 기능 명세서

> **경로**: `/admin/report`
> **최종 업데이트**: 2026-02-27
> **상태**: 운영 중

---

## 1. 개요

관리자가 AI 챗봇 서비스의 사용 현황, 답변 품질, 성능 지표를 한눈에 파악할 수 있는 대시보드입니다.

### 주요 특징
- **7개 섹션**으로 구성된 종합 서비스 리포트
- **날짜 범위 선택기**로 기간별 데이터 조회 (오늘 / 7일 / 30일 / 커스텀)
- **모달 드릴다운**: 인텐트별, 사용자별 상세 대화 이력 조회
- **관리자/테스터 제외**: 환경변수로 제외 사용자 관리 (대시보드 데이터 왜곡 방지)

---

## 2. 아키텍처

```
[Frontend: /admin/report]
    │
    ├── DateRangeSelector  ─→  onRangeChange(dateFrom, dateTo)
    │
    └── fetchAllReportData()  ─→  Promise.all 7개 API 병렬 호출
                                    │
[Backend: /api/v1/admin/report/*]   │
    │                                │
    └── ReportService (singleton)    │
            │                        │
            ├── MySQL: chat_log_new ─┘
            ├── ChromaDB: workspace collections (문서 수 조회)
            └── Disk: pdf_output / xlsx_output / ppt_output (생성물 수)
```

### 데이터 수집 흐름
```
[사용자 채팅 요청]
    ↓
[a2a_streaming.py] → intent_classified 이벤트 → intent, worker_name 캡처
    ↓ _internal_collected 이벤트
[chat.py] → metadata에 is_error, tools_used, image_count 추가
    ↓ background_tasks
[chat_log_service.py] → chat_log_new 테이블에 저장
    (intent, worker_name, response_time_ms 컬럼 포함)
```

---

## 3. 날짜 범위 선택기

**컴포넌트**: `frontend/components/dashboard/date-range-selector.tsx`

| 프리셋 | 동작 |
|--------|------|
| 오늘 | 당일 00:00 ~ 23:59 |
| 7일 | 오늘 기준 7일 전 ~ 오늘 |
| 30일 | 오늘 기준 30일 전 ~ 오늘 |
| 커스텀 | 사용자 지정 시작일 ~ 종료일 |

- 페이지 진입 시 기본값 **7일**로 자동 로드
- 날짜 변경 시 `handleRangeChange` → `fetchAllReportData()` 호출 → 전체 데이터 리프레시
- 새로고침 버튼으로 현재 범위 재조회 가능

---

## 4. 대시보드 섹션 상세

### 4.1 이용 현황 (Usage Overview)

**컴포넌트**: `usage-overview.tsx`
**API**: `GET /api/v1/admin/report/overview`

#### KPI 카드 (3개)
| KPI | 설명 | 아이콘 | 색상 |
|-----|------|--------|------|
| 총 메시지 | 기간 내 전체 메시지 수 | MessageSquare | blue |
| 총 세션 | 기간 내 고유 세션 수 | Activity | green |
| 활성 사용자 | 기간 내 고유 사용자 수 | Users | purple |

#### 차트
- **일별 이용 추이 (라인 차트)**: 메시지 수 / 세션 수 / 사용자 수를 3개 라인으로 표시
- recharts `LineChart` + `ResponsiveContainer` (높이 300px)

---

### 4.2 사용자 랭킹 (User Ranking)

**컴포넌트**: `user-ranking.tsx`
**API**: `GET /api/v1/admin/report/users`

#### KPI 카드 (2개)
| KPI | 설명 | 아이콘 | 색상 |
|-----|------|--------|------|
| 전체 사용자 수 | 기간 내 활성 사용자 수 | Users | blue |
| 사용자당 평균 메시지 | 총 메시지 / 총 사용자 | MessageSquare | green |

#### 상위 10명 막대 차트
- 수평 `BarChart` (layout="vertical"), 메시지 수 기준

#### 사용자별 상세 활동 테이블
| 컬럼 | 설명 |
|------|------|
| 순위 | 1~3위는 금색 뱃지 표시 |
| 사용자 | 사번 (클릭 가능 → 상세 모달) |
| 메시지 수 | 해당 기간 총 메시지 |
| 세션 수 | 해당 기간 고유 세션 |
| 주 사용 기능 | 가장 많이 사용한 인텐트 (unknown 제외) |
| 최근 활동 | 마지막 활동 일시 |

#### 사용자 상세 모달 (User Detail Modal)
**컴포넌트**: `user-detail-modal.tsx`
**API**: `GET /api/v1/admin/report/users/detail?user_id=...`

사용자 행 클릭 시 모달이 열리며, 해당 사용자의 최근 50건 Q&A 이력을 보여줍니다.

| 컬럼 | 설명 |
|------|------|
| 일시 | MM/DD HH:mm 형식 |
| 질문 | 사용자 입력 (최대 150자) |
| 답변 | AI 응답 미리보기 (최대 200자) |
| 분류 | 인텐트 한글 레이블 |
| 응답시간 | ms 단위 (없으면 '-') |

---

### 4.3 인텐트 분류 (Intent Distribution)

**컴포넌트**: `intent-distribution.tsx`
**API**: `GET /api/v1/admin/report/intents`

#### 파이 차트
- recharts `PieChart` + `Cell` 컬러 매핑
- 14개 인텐트 카테고리 + 미분류

#### 인텐트별 테이블
| 컬럼 | 설명 |
|------|------|
| 인텐트 | 한글 레이블 (클릭 가능) |
| 건수 | 해당 인텐트 메시지 수 |
| 비율 | 전체 대비 % |

#### 인텐트 상세 모달 (Intent Detail Modal)
**컴포넌트**: `intent-detail-modal.tsx`
**API**: `GET /api/v1/admin/report/intents/detail?intent_key=...`

인텐트 행 클릭 시 모달이 열리며, 해당 인텐트로 분류된 최근 50건 Q&A 이력을 보여줍니다.

| 컬럼 | 설명 |
|------|------|
| 일시 | MM/DD HH:mm 형식 |
| 사용자 | 사번 |
| 질문 | 사용자 입력 (최대 150자) |
| 답변 | AI 응답 미리보기 (최대 200자) |
| Worker | 처리한 Worker 이름 |
| 응답시간 | ms 단위 |

---

### 4.4 답변 품질 (Quality Metrics)

**컴포넌트**: `quality-metrics.tsx`
**API**: `GET /api/v1/admin/report/quality`

#### KPI 카드 (2개)
| KPI | 설명 | 아이콘 | 색상 |
|-----|------|--------|------|
| 답변 실패 건수 | 기간 내 실패로 판정된 건수 | AlertTriangle | red |
| 답변 실패율 | 실패 / 전체 × 100 (%) | Percent | red |

#### 답변 실패 감지 로직
실패로 판정되는 조건 (OR):
1. `metadata.is_error = true` — 명시적 에러 (시스템 오류, 타임아웃 등)
2. **검색 기반 인텐트**에서 문서를 찾지 못한 경우:
   - 대상 인텐트: `corp_rag`, `it_support`, `acct_support`, `user_files`
   - 패턴: "찾을 수 없", "검색 결과가 없", "관련 정보를 찾지 못", "관련된 정보가 없", "관련 자료가 없", "조회 결과가 없", "해당하는 내용을 찾"

> **주의**: 일반 대화(`direct`), 웹 검색(`web_search`) 등 비-검색 인텐트에서는 위 패턴을 적용하지 않습니다. 이는 오탐(false positive)을 방지하기 위함입니다.

#### 카테고리별 답변 실패율 차트
- 수평 `BarChart`, 인텐트(카테고리)별 실패율 (%)
- 실패율이 높은 카테고리는 빨간색으로 하이라이트

#### 최근 답변 실패 샘플 테이블
| 컬럼 | 설명 |
|------|------|
| 일시 | 발생 시각 |
| 사용자 | 사번 |
| 질문 | 사용자 입력 |
| 답변 (미리보기) | AI 응답 앞부분 |
| 카테고리 | 인텐트 한글 레이블 |

---

### 4.5 워크스페이스 활용 (Workspace Usage)

**컴포넌트**: `workspace-usage.tsx`
**API**: `GET /api/v1/admin/report/workspaces`

#### KPI 카드 (3개)
| KPI | 설명 | 아이콘 | 색상 |
|-----|------|--------|------|
| 활성 워크스페이스 | 기간 내 세션이 있는 워크스페이스 수 | FolderOpen | blue |
| 워크스페이스 세션 | 워크스페이스 내 총 세션 수 | MessageCircle | green |
| 메모리 업데이트 | workspace_memory 갱신 횟수 | Brain | orange |

#### 상위 워크스페이스 테이블
| 컬럼 | 설명 |
|------|------|
| 워크스페이스 | 이름 |
| 사용자 | 소유자 사번 |
| 메시지 | 해당 기간 메시지 수 |
| 문서 수 | ChromaDB 컬렉션 내 문서 수 (실시간 조회) |
| 최근 활동 | 마지막 활동 일시 |

---

### 4.6 파일 & 생성물 (Files & Generated Content)

**컴포넌트**: `files-generated.tsx`
**API**: `GET /api/v1/admin/report/artifacts`

#### KPI 카드 (5개)
| KPI | 설명 | 데이터 소스 |
|-----|------|-------------|
| 파일 업로드 세션 | 파일을 업로드한 고유 세션 수 | `COUNT(DISTINCT session)` where `intent IN ('user_files', 'xlsx')` |
| 이미지 업로드 세션 | 이미지를 업로드한 고유 세션 수 | `COUNT(DISTINCT session)` where `metadata.image_count > 0` |
| PDF 생성 | 기간 내 생성된 PDF 파일 수 | `backend/data/pdf_output/` 디렉토리 스캔 (mtime 기준) |
| XLSX 생성 | 기간 내 생성된 엑셀 파일 수 | `backend/data/xlsx_output/` 디렉토리 스캔 |
| PPT 생성 | 기간 내 생성된 PPT 파일 수 | `backend/data/ppt_output/` 디렉토리 스캔 |

> **파일/이미지 업로드 카운트**: 메시지 단위가 아닌 **세션 단위**로 집계합니다. 한 세션에서 파일 업로드 후 여러 번 대화해도 1건으로 카운트됩니다.

#### 일별 생성 추이 차트
- `BarChart` (stacked), PDF / XLSX / PPT 3개 시리즈
- PDF: 주황(#F59E0B), XLSX: 보라(#8B5CF6), PPT: 파랑(#3B82F6)

---

### 4.7 응답 성능 (Performance)

**컴포넌트**: `performance-section.tsx`
**API**: `GET /api/v1/admin/report/performance`

#### KPI 카드 (2개)
| KPI | 설명 | 아이콘 | 색상 |
|-----|------|--------|------|
| 평균 응답시간 | 전체 평균 (ms → 초 변환 표시) | Timer | blue |
| P95 응답시간 | 95번째 백분위 (Python 정렬 계산) | Zap | orange |

#### 일별 응답시간 추이 차트
- `LineChart`, 평균 + P95 2개 라인

#### Worker별 성능 테이블
| 컬럼 | 설명 |
|------|------|
| Worker | Worker 이름 |
| 평균 (ms) | 평균 응답시간 |
| P95 (ms) | 95번째 백분위 응답시간 |
| 처리 건수 | 해당 Worker 총 처리 건수 |

---

## 5. API 엔드포인트

**기본 경로**: `/api/v1/admin/report`

| 메서드 | 경로 | 파라미터 | 설명 |
|--------|------|----------|------|
| GET | `/overview` | `date_from`, `date_to` | 이용 현황 (KPI + 일별 추이) |
| GET | `/intents` | `date_from`, `date_to` | 인텐트 분포 |
| GET | `/intents/detail` | `date_from`, `date_to`, `intent_key` | 인텐트별 상세 Q&A |
| GET | `/quality` | `date_from`, `date_to` | 답변 품질 지표 |
| GET | `/workspaces` | `date_from`, `date_to` | 워크스페이스 활용 |
| GET | `/artifacts` | `date_from`, `date_to` | 파일 & 생성물 |
| GET | `/performance` | `date_from`, `date_to` | 응답 성능 |
| GET | `/users` | `date_from`, `date_to` | 사용자 랭킹 |
| GET | `/users/detail` | `date_from`, `date_to`, `user_id` | 사용자별 상세 Q&A |

- 날짜 형식: `YYYY-MM-DD`
- 모든 API는 `date_from` ~ `date_to`(포함) 범위 데이터를 반환

---

## 6. 데이터 소스

### MySQL (`chat_log_new` 테이블)
대시보드의 핵심 데이터 소스. 모든 채팅 로그가 저장되며, 아래 컬럼이 리포트용으로 추가됨:

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `intent` | VARCHAR(20) | 인텐트 분류 결과 (e.g., `direct`, `corp_rag`) |
| `worker_name` | VARCHAR(30) | 처리 Worker 이름 |
| `response_time_ms` | INT | 응답 소요 시간 (밀리초) |
| `metadata` | JSON | 부가 정보 (`is_error`, `image_count`, `tools_used` 등) |

### ChromaDB
워크스페이스 섹션에서 각 워크스페이스의 문서 수를 실시간 조회 (`workspace_{uuid}` 컬렉션).

### 파일 시스템
생성물 카운트는 출력 디렉토리의 파일을 수정시간(mtime) 기준으로 필터링하여 집계:
- `backend/data/pdf_output/*.pdf`
- `backend/data/xlsx_output/*.xlsx`
- `backend/data/ppt_output/*.pptx`

---

## 7. 설정 및 환경변수

### 제외 사용자 설정
```env
# 대시보드에서 제외할 사용자 (쉼표 구분)
REPORT_EXCLUDED_USERS=A2304013
```
- 관리자/테스터 계정의 데이터를 대시보드에서 제외하여 지표 왜곡 방지
- 모든 SQL 쿼리에 `AND userId NOT IN (...)` 조건으로 적용
- 기본값: `A2304013`
- 여러 사용자 제외 시: `REPORT_EXCLUDED_USERS=A2304013,A9999999`

### DB 마이그레이션
```bash
# 리포트 컬럼 추가 (최초 1회)
mysql -u root -p < backend/migrations/add_report_columns.sql
```

---

## 8. 인텐트 레이블 매핑

| DB 값 (intent) | 화면 표시 (한글) |
|-----------------|------------------|
| `direct` | 일반 대화 |
| `web_search` | 웹 검색 |
| `corp_rag` | 사내 문서 |
| `user_files` | 파일 검색 |
| `youtube` | YouTube |
| `url_fetch` | URL 추출 |
| `it_support` | IT 지원 |
| `acct_support` | 회계 지원 |
| `visualization` | 시각화 |
| `ppt_generation` | PPT 생성 |
| `xlsx` | 엑셀 |
| `mail` | 메일 |
| `approval` | 전자결재 |
| `board` | 게시판 |
| (null / unknown) | 미분류 |

---

## 9. 프론트엔드 컴포넌트 구조

```
frontend/
├── app/admin/report/
│   └── page.tsx                    # 메인 대시보드 페이지
├── components/dashboard/
│   ├── date-range-selector.tsx     # 날짜 범위 선택기
│   ├── usage-overview.tsx          # 이용 현황 섹션
│   ├── user-ranking.tsx            # 사용자 랭킹 섹션
│   ├── user-detail-modal.tsx       # 사용자 상세 모달
│   ├── intent-distribution.tsx     # 인텐트 분류 섹션
│   ├── intent-detail-modal.tsx     # 인텐트 상세 모달
│   ├── quality-metrics.tsx         # 답변 품질 섹션
│   ├── workspace-usage.tsx         # 워크스페이스 활용 섹션
│   ├── files-generated.tsx         # 파일 & 생성물 섹션
│   ├── performance-section.tsx     # 응답 성능 섹션
│   ├── kpi-card.tsx                # KPI 카드 공통 컴포넌트
│   └── section-header.tsx          # 섹션 헤더 공통 컴포넌트
└── lib/api/
    └── report.ts                   # API 클라이언트 + 타입 정의
```

### 공통 컴포넌트
- **KpiCard**: 아이콘 + 레이블 + 값 표시, 5가지 accent 색상 (blue, green, orange, red, purple, default)
- **SectionHeader**: 한글 제목 + 영문 부제목
- **차트 라이브러리**: recharts (BarChart, LineChart, PieChart, ResponsiveContainer)

---

## 10. 백엔드 서비스 구조

```
backend/app/
├── api/routes/
│   └── report.py                   # API 라우터 (9개 엔드포인트)
└── services/
    └── report_service.py           # ReportService (singleton)
        ├── get_overview()          # 이용 현황
        ├── get_intents()           # 인텐트 분포
        ├── get_intent_detail()     # 인텐트별 상세
        ├── get_quality()           # 답변 품질
        ├── get_workspaces()        # 워크스페이스 활용
        ├── get_artifacts()         # 파일 & 생성물
        ├── get_performance()       # 응답 성능
        ├── get_user_ranking()      # 사용자 랭킹
        └── get_user_detail()       # 사용자별 상세
```

- **싱글톤 패턴**: `get_report_service()` 함수로 인스턴스 관리
- **DB 연결 풀**: `PooledDB` 기반 커서 관리 (`get_database_connection()`)
- **P95 계산**: Python 측에서 정렬 후 인덱스 기반 계산 (MySQL에서 직접 P95 어려움)

---

## 11. UI/UX 디자인 가이드

### 색상 체계
| 용도 | 색상 코드 |
|------|-----------|
| 배경 (메인) | `#0F172A` |
| 배경 (카드) | `#1F2937/50` |
| 테두리 | `#334155` |
| 텍스트 (기본) | `#F3F4F6` |
| 텍스트 (보조) | `#9CA3AF` |
| 텍스트 (약한) | `#6B7280` |
| 강조 (파랑) | `#3B82F6` |
| 강조 (초록) | `#10B981` |
| 강조 (주황) | `#F59E0B` |
| 강조 (빨강) | `#EF4444` |
| 강조 (보라) | `#8B5CF6` |

### 레이아웃
- 최대 너비: `max-w-7xl` (1280px)
- 반응형 그리드: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3~5`
- 헤더: sticky top-0, backdrop-blur
- 섹션 간격: `space-y-10`

---

## 12. 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-02-23 | 초기 구현 (6개 섹션, 6개 API) |
| 2026-02-27 | 사용자 랭킹 섹션 추가 |
| 2026-02-27 | 사용자 상세 모달 추가 (클릭 → Q&A 이력) |
| 2026-02-27 | 관리자/테스터 제외 기능 (`REPORT_EXCLUDED_USERS`) |
| 2026-02-27 | 답변 실패 감지 로직 개선 (RAG 인텐트 한정) |
| 2026-02-27 | 파일/이미지 업로드 → 세션 단위 카운트로 변경 |
| 2026-02-27 | 주 사용 기능에서 unknown 제외 |
