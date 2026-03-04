# User Memory 최적화 (2026-02-27)

## 문제점

### 1. 불필요한 fact 적재
user_memory 테이블에 LLM(Haiku)이 "추출할 사실이 없다"는 설명문을 fact로 저장하는 문제 발생.

**실제 저장된 불필요 데이터 예시:**
```json
{"content": "(사용자가 \"ㅎㅇ\"만 입력했으며, 이는 인사 메시지로 새로운 개인적 특성을 드러내지 않습니다.)"}
{"content": "추출할 새로운 개인적 특성이 없습니다."}
{"content": "(대화 내용이 반복적인 엑셀 작업 요청...없습니다.)"}
{"content": "# 김용국님의 개인적 특성"}
```

### 2. 신원정보(이름/부서) 밀림 위험
- `all_facts[-20:]`로 FIFO 방식 유지 → 오래된 fact부터 탈락
- 이름, 부서 같은 영구 보존 정보가 가장 오래된 항목이라 밀려날 수 있음

---

## 해결 1: 불필요 fact 필터링 (적용 완료)

### 프롬프트 강화 (`memory_service.py`)
- 워크스페이스/사용자 메모리 양쪽 프롬프트에 적용
- 기존: `"추출할 사실이 없으면 빈 줄만 출력하세요"`
- 변경: `"추출할 사실이 없으면 "NONE"만 출력하세요. 괄호 안 설명, 이유, 코멘트 등을 절대 쓰지 마세요."`

### 후처리 필터 추가 (belt-and-suspenders)
`_extract_key_facts()`, `_extract_user_facts()` 양쪽에 동일 적용:

```python
# "NONE" 응답
if line.upper() == "NONE":
    continue
# 괄호로 감싼 설명문 (예: "(추출할 특성이 없습니다)")
if line.startswith("(") and line.endswith(")"):
    continue
# "없습니다" 류 설명문
if any(kw in line for kw in ["없습니다", "추출할", "드러내지 않", "해당하는", "발견되지"]):
    continue
# 마크다운 헤더
if line.startswith("#"):
    continue
```

### 필터 적용 결과

| 기존 저장된 내용 | 걸리는 필터 |
|---|---|
| `(사용자가 "ㅎㅇ"만 입력했으며...드러내지 않습니다.)` | 괄호 + "드러내지 않" |
| `추출할 새로운 개인적 특성이 없습니다.` | "추출할" + "없습니다" |
| `(추출할 새로운 개인적 특성이 없습니다.)` | 괄호 + "추출할" + "없습니다" |
| `# 김용국님의 개인적 특성` | `#` 헤더 |

---

## 해결 2: 신원정보 DB 캐시 분리 (설계 완료, 미구현)

### 방향
- 이름/부서/직책 → 그룹웨어 PostgreSQL에서 직접 조회 + 인메모리 캐시
- user_memory → 행동 선호도만 저장 (슬롯 낭비 방지)

### 인메모리 캐시 구조
```python
# 모듈 전역 변수 (프로세스 수명)
_user_profile_cache: Dict[str, dict] = {}

async def get_user_profile(employee_number: str) -> Optional[dict]:
    # 캐시 히트 → 바로 반환
    if employee_number in _user_profile_cache:
        return _user_profile_cache[employee_number]

    # 캐시 미스 → PostgreSQL(go_users) 조회 (사용자당 1회만)
    pool = await get_tims_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT login_id, name, dept_name, position_name
            FROM go_users WHERE employee_number = $1
        """, employee_number)

    if not row:
        return None

    profile = {
        "name": row["name"],
        "dept": row["dept_name"],
        "title": row["position_name"],
        "login_id": row["login_id"],
    }
    _user_profile_cache[employee_number] = profile
    return profile
```

### 오케스트레이터 흐름 (변경 후)
```
사용자 요청 (user_id)
    ↓
Phase 0:  프로필 캐시 확인 → 없으면 PostgreSQL 조회 → 캐시 저장
Phase 0a: user_memory에서 행동 선호도 facts 로드 (MySQL)
Phase 0b: workspace_memory에서 요약 + facts 로드 (MySQL)
    ↓
Worker에 3개 모두 전달
    ↓
build_system_prompt()에서 조립:
    ## 사용자 정보        ← DB 캐시 (확정, 불변)
    - 이름: 김용국
    - 부서: IT운영팀

    ## 사용자 선호도      ← user_memory (LLM 추출, 가변)
    - 데이터 기반 분석 선호
    - 직설적 피드백 선호

    ## 워크스페이스 컨텍스트 ← workspace_memory (롤링 요약)
    AWS VDI PoC 진행 중...
```

### 캐시 특성

| 항목 | 설명 |
|---|---|
| 저장 위치 | Python dict (프로세스 메모리) |
| 캐시 키 | 사번 (employee_number) |
| 캐시 값 | `{name, dept, title, login_id}` |
| 수명 | 서버 프로세스 재시작까지 |
| DB 조회 | 사용자당 1회 (첫 요청 시) |
| 별도 테이블 | 불필요 — 기존 go_users 재사용 |
| 기존 패턴 | `approval_mcp_server.py`의 `_user_info_cache`와 동일 |

### 추출 프롬프트 변경 (구현 시)
```
**절대 추출하지 않는 것:**
- 이름, 부서, 직책 (시스템에서 자동 제공)  ← 추가
- 일회성 질문이나 작업 내용
- 특정 프로젝트의 세부사항
```

---

## 메모리 시스템 전체 구조 (현행 분석)

### 워크스페이스 메모리 (`WorkspaceMemoryService`)
- 트리거: (총 메시지 - 마지막 요약 시점) >= 10
- 최근 20개 메시지 로드 (THRESHOLD * 2)
- 롤링 요약: 기존 요약 + 최근 메시지 → 새 요약 (500자 이내)
- key_facts: 최대 10개, `all_facts[-10:]` (FIFO)

### 사용자 전역 메모리 (`UserMemoryService`)
- 트리거: (총 메시지 - 마지막 추출 시점) >= 20
- 최근 40개 메시지 로드 (THRESHOLD * 2)
- key_facts만: 최대 20개, 1회 최대 3개 신규
- `[업데이트] old → new` 문법으로 기존 fact 교체 가능
- `all_facts[-20:]` (FIFO)

### 데이터 출처 분리 (목표 상태)

| 정보 종류 | 출처 | 수명 |
|---|---|---|
| 이름/부서/직책 | 그룹웨어 DB (PostgreSQL) | 프로세스 캐시 (재시작 시 갱신) |
| 행동 선호도 | user_memory (LLM 추출) | MySQL 영속 (최대 20개) |
| 프로젝트 맥락 | workspace_memory (롤링 요약) | MySQL 영속 (워크스페이스별) |
