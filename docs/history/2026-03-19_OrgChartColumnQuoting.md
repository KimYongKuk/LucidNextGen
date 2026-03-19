# 2026-03-19 OrgChart MCP — 부서ID 컬럼 따옴표 자동 치환

## 개요
PostgreSQL의 identifier folding으로 인해 `부서ID` 컬럼이 `부서id`로 변환되어 "column does not exist" 에러 발생. 계층 조회의 핵심 Step 1(부서ID 획득)이 매번 실패하면서 LLM이 10회 tool call을 소진하고 정확한 답을 내지 못하는 문제 수정.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/mcp_servers/org_chart_mcp_server.py` | 수정 | SQL 실행 전 `부서ID` → `"부서ID"` 자동 따옴표 치환 |

## 상세 내용

### 문제 분석
- PostgreSQL은 따옴표 없는 식별자를 **소문자로 fold** (SQL 표준)
- VIEW `v_org_chart`가 `"부서ID"` (따옴표 포함)로 생성됨 → 대소문자 보존
- LLM이 스키마 가이드대로 `SELECT 부서ID ...` 생성 → PostgreSQL이 `부서id`로 해석 → 에러
- 계층 조회 Step 1 (`부서ID` + `부서경로` 조회)이 반드시 실패
- LLM이 `부서ID` 없이 `부서경로`만으로 계층을 역추적하려 10회 삽질 (49초, 116K 토큰)

### 실제 로그 (2026-03-19 13:27:53)
```
[SQL QUERY] SELECT DISTINCT 부서ID, 부서, 부서경로 FROM v_org_chart WHERE 부서 ILIKE '%정보보안%'
→ DB 오류: column "부서id" does not exist
(이후 9회 재시도, max_agent_steps=20 한도 도달)
```

### 수정 내용
`org_chart_mcp_server.py`의 SQL 실행 직전에 regex 치환 추가:
```python
sql_query = re.sub(r'(?<!")부서ID(?!")', '"부서ID"', sql_query)
```
- `부서ID` → `"부서ID"` (따옴표 추가)
- 이미 따옴표로 감싸진 경우 건너뜀 (negative lookahead/lookbehind)
- 다른 한글 컬럼(이름, 직책, 부서, 부서경로, 직무, 메모_근무지)은 소문자만이므로 fold 영향 없음

## 결정 사항 및 주의점
- **MCP 서버 레벨 치환**: LLM 프롬프트에서 따옴표를 강제하는 것보다 확실함 (LLM은 따옴표를 잘 넣지 않음)
- 향후 대소문자 혼합 컬럼이 추가되면 동일 패턴으로 치환 규칙 추가 필요
- VIEW 재생성 시 소문자 컬럼명으로 통일하면 근본적 해결 가능 (DBA 협의 필요)
