# 스케줄 조회 기능 구현 완료 📅

> 메타데이터 기반 그룹웨어 캘린더 조회 시스템

---

## ✅ 완료된 작업

### 1. **RLS 관련 코드 제거**
- ✅ `postgres_security_service.py` 삭제
- ✅ `postgres_tool_wrapper.py` 삭제
- ✅ `postgres_secure_server.py` 삭제
- ✅ `setup_row_level_security.sql` 삭제
- ✅ `POSTGRES_SECURITY_GUIDE.md` 삭제
- ✅ `SIMPLE_SETUP_GUIDE.md` 삭제

### 2. **메타데이터 파일 생성**
- ✅ `backend/metadata/` 폴더 생성
- ✅ `MCP_GW_SCHEDULE.md` 작성
  - 테이블 스키마 정의
  - 샘플 쿼리 7개
  - 주의사항 및 사용 예시
  - PostgreSQL 날짜 함수 가이드

### 3. **Schedule MCP 서버 구현**
- ✅ `schedule_mcp_server.py` 생성
- ✅ 5개 도구 구현:
  1. `get_schedule_metadata` - 메타데이터 조회
  2. `query_schedule` - SQL 쿼리 실행 (준비됨)
  3. `get_today_schedule` - 오늘 일정
  4. `search_schedule` - 키워드 검색
  5. `get_week_schedule` - 주간 일정

### 4. **MCP 설정 업데이트**
- ✅ `mcp_config.json`에 schedule 서버 추가
- ✅ postgres 서버 제거

### 5. **테스트 완료**
- ✅ Schedule MCP 서버 단독 실행 성공
- ✅ MCP Adapter에서 도구 로드 확인
- ✅ 총 11개 도구 로드 (tavily 4 + rag 2 + schedule 5)

---

## 📂 파일 구조

```
backend/
├── metadata/
│   └── MCP_GW_SCHEDULE.md          ⭐ 스케줄 테이블 메타데이터
│
├── app/
│   └── mcp_servers/
│       ├── rag_server.py            (기존)
│       └── schedule_mcp_server.py   ⭐ 스케줄 조회 MCP 서버
│
└── mcp_config.json                  (업데이트됨)
```

---

## 🛠️ 구현된 도구 목록

### **Schedule MCP 서버 (5개 도구)**

#### 1. `get_schedule_metadata()`
메타데이터 전체 내용 반환 (MCP_GW_SCHEDULE.md)

**사용 시점:**
- AI가 스키마를 모를 때
- 쿼리 작성 방법을 알아야 할 때

---

#### 2. `query_schedule(user_id, sql_query)`
직접 SQL 쿼리 실행 (준비 단계)

**매개변수:**
- `user_id`: 사용자 ID
- `sql_query`: SELECT 쿼리

**예시:**
```python
query_schedule(
    user_id="emp001",
    sql_query="SELECT * FROM schedules WHERE user_id = 'emp001' AND DATE(start_time) = CURRENT_DATE"
)
```

---

#### 3. `get_today_schedule(user_id)`
오늘 일정 조회 (간편 도구)

**사용 시점:**
- "오늘 일정 뭐야?"
- "오늘 회의 있어?"
- "오늘 스케줄 보여줘"

**생성되는 SQL:**
```sql
SELECT title, time, location, status
FROM schedules
WHERE user_id = '{user_id}'
  AND DATE(start_time) = CURRENT_DATE
  AND status != 'cancelled'
ORDER BY start_time ASC;
```

---

#### 4. `search_schedule(user_id, keyword, days_range=30)`
키워드로 일정 검색

**사용 시점:**
- "회의 관련 일정 찾아줘"
- "프로젝트 일정 검색"

**매개변수:**
- `keyword`: 검색어
- `days_range`: 검색 기간 (기본 30일)

---

#### 5. `get_week_schedule(user_id, week_offset=0)`
주간 일정 조회

**사용 시점:**
- "이번 주 일정 보여줘" (week_offset=0)
- "다음 주 일정은?" (week_offset=1)
- "지난 주 일정" (week_offset=-1)

---

## 🎯 사용 예시

### **시나리오 1: 오늘 일정 조회**

**사용자 질문:**
```
"오늘 일정 뭐야?"
```

**AI 동작:**
1. `get_today_schedule(user_id="emp001")` 호출
2. SQL 쿼리 생성
3. (향후) PostgreSQL 실행 → 결과 반환

**현재 응답:**
```
📅 오늘 일정 조회 요청

생성된 SQL:
SELECT title, time, location, status
FROM schedules
WHERE user_id = 'emp001'
  AND DATE(start_time) = CURRENT_DATE
  ...

⚠️ 실제 데이터 조회를 위해서는 PostgreSQL 연결이 필요합니다.
```

---

### **시나리오 2: 주간 일정 조회**

**사용자 질문:**
```
"이번 주 회의 일정 정리해줘"
```

**AI 동작:**
1. `get_week_schedule(user_id="emp001", week_offset=0)` 호출
2. 주간 SQL 쿼리 생성
3. (향후) 결과를 요약하여 응답

---

### **시나리오 3: 키워드 검색**

**사용자 질문:**
```
"프로젝트 관련 일정 찾아줘"
```

**AI 동작:**
1. `search_schedule(user_id="emp001", keyword="프로젝트")` 호출
2. ILIKE 검색 쿼리 생성
3. (향후) 검색 결과 반환

---

## 🚀 다음 단계 (PostgreSQL 연결)

### **Phase 1: 데이터베이스 연결 설정**

`schedule_mcp_server.py`에 추가:

```python
import asyncpg

# PostgreSQL 연결 풀
DB_POOL = None

async def init_db():
    global DB_POOL
    DB_POOL = await asyncpg.create_pool(
        "postgres://api:password@192.168.100.5:5432/tims",
        min_size=2,
        max_size=10
    )

async def execute_query(sql: str) -> List[dict]:
    async with DB_POOL.acquire() as conn:
        rows = await conn.fetch(sql)
        return [dict(row) for row in rows]
```

### **Phase 2: query_schedule 함수 업데이트**

```python
@mcp.tool()
async def query_schedule(user_id: str, sql_query: str) -> str:
    # 검증
    if not sql_query.upper().startswith('SELECT'):
        return "❌ SELECT 쿼리만 허용"

    # 실행
    try:
        results = await execute_query(sql_query)

        if not results:
            return "조회 결과가 없습니다."

        # 포맷팅
        formatted = format_schedule_results(results)
        return formatted

    except Exception as e:
        return f"❌ 쿼리 실행 오류: {str(e)}"
```

### **Phase 3: 결과 포맷팅**

```python
def format_schedule_results(results: List[dict]) -> str:
    output = f"📅 일정 {len(results)}건\n\n"

    for idx, row in enumerate(results, 1):
        title = row.get('title', 'N/A')
        start = row.get('start_time', row.get('time', 'N/A'))
        location = row.get('location', '-')

        output += f"{idx}. {title}\n"
        output += f"   ⏰ {start}\n"
        output += f"   📍 {location}\n\n"

    return output
```

---

## 📋 체크리스트

### **완료됨 ✅**
- [x] RLS 코드 제거
- [x] 메타데이터 파일 작성
- [x] Schedule MCP 서버 구현
- [x] MCP 설정 업데이트
- [x] 도구 로드 테스트

### **다음 단계 (선택)**
- [ ] PostgreSQL 연결 추가
- [ ] 실제 데이터 조회 테스트
- [ ] 에러 핸들링 강화
- [ ] 결과 포맷팅 개선
- [ ] 캐싱 추가 (성능 최적화)

---

## 💡 핵심 아이디어

### **메타데이터 기반 접근**

```
MCP_GW_SCHEDULE.md (메타데이터)
    ↓
AI가 읽고 이해
    ↓
적절한 SQL 쿼리 생성
    ↓
schedule_mcp_server.py 실행
    ↓
(향후) PostgreSQL 조회
    ↓
사용자에게 결과 반환
```

### **장점:**
1. ✅ **코드 수정 없이 메타데이터만 업데이트**
   - 테이블 스키마 변경 → MD 파일만 수정
   - 새 샘플 쿼리 추가 → MD 파일에 추가

2. ✅ **확장성**
   - 이메일: `MCP_GW_EMAIL.md` 추가
   - 전자결재: `MCP_GW_APPROVAL.md` 추가
   - 게시판: `MCP_GW_BOARD.md` 추가

3. ✅ **유지보수 용이**
   - 메타데이터와 코드 분리
   - Git으로 변경 이력 추적
   - 문서로도 활용 가능

---

## 🎉 현재 상태

**스케줄 조회 기능 완성! (메타데이터 + MCP 서버)**

**현재 가능한 것:**
- ✅ AI가 메타데이터 읽기
- ✅ 적절한 SQL 쿼리 생성
- ✅ 5가지 스케줄 조회 도구 제공

**다음 단계:**
- PostgreSQL 연결 추가
- 실제 데이터 조회

---

**작성일:** 2025-01-18
**버전:** 1.0
**상태:** ✅ 완료 (DB 연결 대기)
