"""조직도/담당자 검색 MCP 서버

v_org_chart 뷰를 통해 사내 직원의 부서, 직책, 직무, 근무지 정보를 검색합니다.
"""
import sys
import os
import asyncpg
import re
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastmcp import FastMCP

mcp = FastMCP("Org Chart Server v1")

# PostgreSQL 연결 정보 (TIMS DB - IT/ACCT VOC와 동일)
DATABASE_URL = "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims"

# 전역 연결 풀
_db_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    """PostgreSQL 연결 풀 가져오기 (싱글톤)"""
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30
        )
        print("Org Chart DB 연결 풀 생성 완료", file=sys.stderr)
    return _db_pool


@mcp.tool()
async def execute_org_chart_query(sql_query: str) -> str:
    """조직도 SQL 실행. SELECT만 허용, v_org_chart 뷰 사용.
    컬럼명은 반드시 한글: 이름, 직책, 부서, 직무, 메모_근무지.
    예: SELECT 이름, 직책, 부서, 직무, 메모_근무지 FROM v_org_chart WHERE 부서 IS NOT NULL AND 이름 ILIKE '%홍길동%'"""
    print("\n" + "="*80, file=sys.stderr)
    print("[Org Chart MCP] 쿼리 요청 수신", file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"받은 쿼리:\n{sql_query}", file=sys.stderr)
    print("="*80 + "\n", file=sys.stderr)

    validation_steps = []

    validation_steps.append("[실행된 SQL 쿼리]")
    validation_steps.append(f"```sql\n{sql_query}\n```")
    validation_steps.append("")

    # 검증 1: SELECT만 허용
    validation_steps.append("1단계: SELECT 쿼리 검증")
    print("[검증 1/4] SELECT 쿼리 확인 중...", file=sys.stderr)
    if not sql_query.strip().upper().startswith('SELECT'):
        print("[검증 1/4] 실패: SELECT가 아닌 쿼리\n", file=sys.stderr)
        validation_steps.append("   실패: SELECT 쿼리만 허용됩니다")
        return "\n".join(validation_steps) + "\n\n오류: SELECT 쿼리만 실행 가능합니다."
    print("[검증 1/4] 통과\n", file=sys.stderr)
    validation_steps.append("   통과")

    # 검증 2: v_org_chart 뷰 확인
    validation_steps.append("2단계: 대상 뷰 확인")
    print("[검증 2/4] 대상 뷰 확인 중...", file=sys.stderr)
    query_upper = sql_query.upper()
    if 'V_ORG_CHART' not in query_upper:
        print("[검증 2/4] 실패: v_org_chart 뷰 미사용\n", file=sys.stderr)
        validation_steps.append("   실패: v_org_chart 뷰를 사용해야 합니다")
        return "\n".join(validation_steps) + "\n\n오류: v_org_chart 뷰만 접근 가능합니다.\n가이드의 쿼리 예제를 참고하세요."
    print("[검증 2/4] 통과\n", file=sys.stderr)
    validation_steps.append("   통과")

    # 검증 3: 부서 IS NOT NULL 권장 (경고만)
    validation_steps.append("3단계: 부서 필터 확인")
    print("[검증 3/4] 부서 필터 확인 중...", file=sys.stderr)
    if '부서' not in sql_query or 'IS NOT NULL' not in query_upper:
        print("[검증 3/4] 경고: 부서 IS NOT NULL 조건 누락\n", file=sys.stderr)
        validation_steps.append("   경고: 부서 IS NOT NULL 조건을 추가하면 활성 직원만 조회됩니다")
    else:
        print("[검증 3/4] 통과\n", file=sys.stderr)
        validation_steps.append("   통과")

    # 검증 4: 위험한 SQL 명령어
    validation_steps.append("4단계: 위험 SQL 명령어 스캔")
    print("[검증 4/4] 위험 SQL 명령어 스캔 중...", file=sys.stderr)

    dangerous_patterns = [
        r'\bDROP\b',
        r'\bDELETE\b',
        r'\bUPDATE\b',
        r'\bINSERT\b',
        r'\bTRUNCATE\b',
        r'\bALTER\b',
        r'\bCREATE\b',
        r';.*(DROP|DELETE|UPDATE|INSERT|TRUNCATE)',
    ]

    found_dangerous = []
    for pattern in dangerous_patterns:
        if re.search(pattern, query_upper):
            keyword = pattern.replace(r'\b', '').replace('\\', '')
            found_dangerous.append(keyword)

    if found_dangerous:
        print(f"[검증 4/4] 실패: 금지된 SQL 명령어 - {', '.join(found_dangerous)}\n", file=sys.stderr)
        validation_steps.append(f"   실패: 금지된 SQL 명령어 발견 - {', '.join(found_dangerous)}")
        return "\n".join(validation_steps) + f"\n\n오류: 읽기 전용(SELECT)만 허용됩니다. 금지된 명령어: {', '.join(found_dangerous)}"
    print("[검증 4/4] 통과 (읽기 전용 쿼리 확인)\n", file=sys.stderr)
    validation_steps.append("   통과 (읽기 전용 쿼리 확인)")

    # 실제 PostgreSQL 쿼리 실행
    validation_steps.append("5단계: PostgreSQL 쿼리 실행")

    print("\n" + "="*80, file=sys.stderr)
    print("[Org Chart MCP] SQL 쿼리 실행", file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"쿼리:\n{sql_query}", file=sys.stderr)
    print("="*80 + "\n", file=sys.stderr)

    try:
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql_query)

            print(f"[Org Chart MCP] 쿼리 실행 성공: {len(rows)}건 조회됨\n", file=sys.stderr)

            if not rows:
                validation_steps.append("   결과: 0건")
                return "\n".join(validation_steps) + "\n\n조회된 직원 정보가 없습니다.\n\n키워드를 유의어로 변경하여 재검색해보세요.\n(예: '인사팀' → 'HR' or '인사' or '경영지원')"

            validation_steps.append(f"   성공: {len(rows)}건 조회됨")

            # 허용된 컬럼만 반환 (사번 등 개인정보 제외)
            ALLOWED_COLUMNS = {'이름', '직책', '부서', '직무', '메모_근무지', '인원수'}
            first_row = dict(rows[0])
            all_columns = list(first_row.keys())
            columns = [col for col in all_columns if col in ALLOWED_COLUMNS]
            if not columns:
                columns = all_columns  # 집계 쿼리 등 fallback

            result_text = "\n".join(validation_steps) + f"\n\n조직도 검색 결과 ({len(rows)}건)\n\n"
            result_text += "| " + " | ".join(str(col) for col in columns) + " |\n"
            result_text += "|" + "|".join("---" for _ in columns) + "|\n"

            for row in rows:
                row_dict = dict(row)
                values = [str(row_dict.get(col, '') or '') for col in columns]
                result_text += "| " + " | ".join(values) + " |\n"

            return result_text.strip()

    except asyncpg.PostgresError as e:
        print(f"[Org Chart MCP] DB 오류: {str(e)}\n", file=sys.stderr)
        validation_steps.append(f"   DB 오류: {str(e)[:100]}")
        return "\n".join(validation_steps) + f"\n\n데이터베이스 오류: {str(e)}"
    except Exception as e:
        print(f"[Org Chart MCP] 실행 실패: {str(e)}\n", file=sys.stderr)
        validation_steps.append(f"   실행 실패: {str(e)[:100]}")
        return "\n".join(validation_steps) + f"\n\n쿼리 실행 실패: {str(e)}"


if __name__ == "__main__":
    print("Org Chart MCP Server v1 시작...", file=sys.stderr)
    print("이 서버는 사내 조직도/담당자 정보를 검색합니다.", file=sys.stderr)
    print("v_org_chart 뷰를 통해 직원 정보를 조회합니다.", file=sys.stderr)
    print("", file=sys.stderr)

    mcp.run(transport="stdio")
