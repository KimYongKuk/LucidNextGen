"""전자결재 조회 MCP 서버

사용자의 전자결재 문서를 조회하는 MCP 서버입니다.
- PostgreSQL(TIMS DB)의 v_appr_* 뷰를 통해 결재 데이터 조회
- 2개 도구: get_user_approval_info, execute_approval_query
"""
import sys
import os
import asyncpg
import re
import html
from typing import Optional, Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastmcp import FastMCP

# doc_body 본문 처리 상수
DOC_BODY_MAX_LENGTH = 8000  # 본문 텍스트 최대 길이 (HTML 태그 제거 후, base_worker compact가 이전 결과 압축)


def _strip_html_tags(html_content: str) -> str:
    """HTML 태그를 제거하고 순수 텍스트만 추출"""
    if not html_content:
        return ""
    # HTML 엔티티 디코딩
    text = html.unescape(html_content)
    # <br>, <p>, <div>, <li> 등을 줄바꿈으로 변환
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div|li|tr|h[1-6])>', '\n', text, flags=re.IGNORECASE)
    # 나머지 HTML 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    # 연속 공백/줄바꿈 정리
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def _truncate_doc_body(value: str) -> str:
    """doc_body HTML을 텍스트로 변환하고 길이 제한 적용"""
    text = _strip_html_tags(value)
    if len(text) > DOC_BODY_MAX_LENGTH:
        return text[:DOC_BODY_MAX_LENGTH] + f"\n\n... (본문이 길어 {DOC_BODY_MAX_LENGTH}자까지만 표시)"
    return text


mcp = FastMCP("Approval Query Server v1")

# PostgreSQL 연결 정보 (TIMS DB)
DATABASE_URL = os.environ.get(
    "TIMS_DATABASE_URL",
    "postgres://ai_reader:Aitf1234$$@192.168.100.5:5432/tims"
)

# 전역 연결 풀
_db_pool: Optional[asyncpg.Pool] = None

# 사용자 정보 캐시 (사번 → {user_id, login_id, name, dept_id, dept_name})
_user_info_cache: Dict[str, dict] = {}

# 허용된 뷰 목록 (화이트리스트)
ALLOWED_VIEWS = [
    'V_APPR_USER_DRAFTED',
    'V_APPR_USER_PENDING',
    'V_APPR_USER_APPROVED',
    'V_APPR_USER_REFERENCED',
    'V_APPR_USER_REDRAFTED',
    'V_APPR_USER_ACCESSIBLE_DEPTS',
    'V_APPR_DEPT_COMPLETED',
    'V_APPR_DEPT_RECEIVED',
    'V_APPR_DEPT_REFERENCED',
    'V_APPR_DOC_PROGRESS',
    'V_USER_INFO_MAPPING',
]


async def _init_connection(conn):
    """각 커넥션에 DateStyle 자동 설정"""
    await conn.execute("SET DateStyle = 'ISO, YMD'")


async def get_db_pool() -> asyncpg.Pool:
    """PostgreSQL 연결 풀 가져오기 (싱글톤)"""
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
            init=_init_connection,
        )
        print("Approval DB 연결 풀 생성 완료", file=sys.stderr)
    return _db_pool


@mcp.tool()
async def get_user_approval_info(employee_number: str) -> str:
    """사번으로 전자결재용 사용자 정보를 조회합니다 (login_id, user_id, dept_id).
    employee_number: 사용자 사번 (예: PA2601004)
    반드시 execute_approval_query 호출 전에 먼저 호출하세요."""

    print(f"\n[Approval MCP] 사용자 정보 조회: {employee_number}", file=sys.stderr)

    # 캐시 확인
    if employee_number in _user_info_cache:
        cached = _user_info_cache[employee_number]
        print(f"[Approval MCP] 캐시 히트: {cached}", file=sys.stderr)
        return (
            f"사용자 정보:\n"
            f"- 이름: {cached['name']}\n"
            f"- 사번(login_id): {cached['login_id']}\n"
            f"- user_id: {cached['user_id']}\n"
            f"- 부서 ID(dept_id): {cached['dept_id']}\n"
            f"- 부서명: {cached['dept_name']}"
        )

    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, login_id, name, dept_id, dept_name
                FROM v_user_info_mapping
                WHERE employee_number = $1
                """,
                employee_number
            )

        if not row:
            print(f"[Approval MCP] 사용자 미발견: {employee_number}", file=sys.stderr)
            return f"오류: 사번 '{employee_number}'에 해당하는 사용자를 찾을 수 없습니다."

        info = {
            "user_id": row["user_id"],
            "login_id": row["login_id"],
            "name": row["name"],
            "dept_id": row["dept_id"],
            "dept_name": row["dept_name"],
        }
        _user_info_cache[employee_number] = info
        print(f"[Approval MCP] 사용자 조회 완료: {info}", file=sys.stderr)

        return (
            f"사용자 정보:\n"
            f"- 이름: {info['name']}\n"
            f"- 사번(login_id): {info['login_id']}\n"
            f"- user_id: {info['user_id']}\n"
            f"- 부서 ID(dept_id): {info['dept_id']}\n"
            f"- 부서명: {info['dept_name']}"
        )

    except Exception as e:
        print(f"[Approval MCP] 사용자 조회 실패: {e}", file=sys.stderr)
        return f"사용자 정보 조회 실패: {str(e)}"


@mcp.tool()
async def execute_approval_query(employee_number: str, sql_query: str) -> str:
    """전자결재 SQL 실행. SELECT만 허용, v_appr_* 뷰 사용.
    반드시 get_user_approval_info를 먼저 호출하여 login_id, dept_id를 확인한 후 사용하세요.
    employee_number: 사용자 사번 (get_user_approval_info와 동일한 값 사용)
    sql_query: 실행할 SELECT 쿼리 (v_appr_* 뷰만 접근 가능)
    DateStyle은 서버에서 자동 설정되므로 SET DateStyle 불필요."""

    # 쿼리 수신 로그
    print("\n" + "=" * 80, file=sys.stderr)
    print("[Approval MCP] 쿼리 요청 수신", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(f"사번: {employee_number}", file=sys.stderr)
    print(f"받은 쿼리:\n{sql_query}", file=sys.stderr)
    print("=" * 80 + "\n", file=sys.stderr)

    validation_steps = []

    # 검증 0: 사용자 인증 확인 (캐시 미스 시 자동 조회)
    if employee_number not in _user_info_cache:
        print(f"[Approval MCP] 캐시 미스: 사번 {employee_number} → 자동 조회 시작", file=sys.stderr)
        try:
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT user_id, login_id, name, dept_id, dept_name
                    FROM v_user_info_mapping
                    WHERE employee_number = $1
                    """,
                    employee_number
                )
            if not row:
                print(f"[Approval MCP] 인증 실패: 사번 {employee_number} 미발견", file=sys.stderr)
                return f"오류: 사번 '{employee_number}'에 해당하는 사용자를 찾을 수 없습니다."
            _user_info_cache[employee_number] = {
                "user_id": row["user_id"],
                "login_id": row["login_id"],
                "name": row["name"],
                "dept_id": row["dept_id"],
                "dept_name": row["dept_name"],
            }
            print(f"[Approval MCP] 자동 조회 완료: {_user_info_cache[employee_number]}", file=sys.stderr)
        except Exception as e:
            print(f"[Approval MCP] 자동 조회 실패: {e}", file=sys.stderr)
            return f"오류: 사용자 정보 조회 실패 - {str(e)}"

    cached_user = _user_info_cache[employee_number]
    auth_login_id = str(cached_user['login_id'])
    auth_user_id = str(cached_user['user_id'])
    auth_dept_id = str(cached_user['dept_id'])
    print(f"[Approval MCP] 인증된 사용자: login_id={auth_login_id}, user_id={auth_user_id}, dept_id={auth_dept_id}", file=sys.stderr)

    # 실행된 쿼리 기록
    validation_steps.append("[실행된 SQL 쿼리]")
    validation_steps.append(f"```sql\n{sql_query}\n```")
    validation_steps.append("")

    query_upper = sql_query.strip().upper()

    # 검증 1: SELECT만 허용
    validation_steps.append("1단계: SELECT 쿼리 검증")
    print("[검증 1/5] SELECT 쿼리 확인 중...", file=sys.stderr)
    if not query_upper.startswith('SELECT'):
        print("[검증 1/5] 실패: SELECT가 아닌 쿼리\n", file=sys.stderr)
        validation_steps.append("   실패: SELECT 쿼리만 허용됩니다")
        return "\n".join(validation_steps) + "\n\n오류: SELECT 쿼리만 실행 가능합니다."
    print("[검증 1/5] 통과\n", file=sys.stderr)
    validation_steps.append("   통과")

    # 검증 2: 허용된 뷰 사용 확인
    validation_steps.append("2단계: 대상 뷰 확인")
    print("[검증 2/5] 대상 뷰 확인 중...", file=sys.stderr)
    found_view = False
    for view in ALLOWED_VIEWS:
        if view in query_upper:
            found_view = True
            break
    if not found_view:
        print("[검증 2/5] 실패: 허용된 v_appr_* 뷰 미사용\n", file=sys.stderr)
        validation_steps.append("   실패: v_appr_* 뷰를 사용해야 합니다")
        allowed_list = ", ".join(v.lower() for v in ALLOWED_VIEWS)
        return "\n".join(validation_steps) + f"\n\n오류: 허용된 뷰만 접근 가능합니다.\n허용 뷰: {allowed_list}"
    print("[검증 2/5] 통과\n", file=sys.stderr)
    validation_steps.append("   통과")

    # 검증 3: 인증된 사용자 ID 포함 확인 (보안 - 차단)
    validation_steps.append("3단계: 인증된 사용자 필터 확인")
    print("[검증 3/5] 인증된 사용자 필터 확인 중...", file=sys.stderr)

    # 쿼리에 인증된 사용자의 login_id, user_id, dept_id, employee_number 중 하나가 포함되어야 함
    query_str = sql_query  # 대소문자 원본 유지하여 값 비교
    has_auth_id = (
        f"'{auth_login_id}'" in query_str  # login_id = 'wg0403'
        or f"= {auth_user_id}" in query_str  # user_id = 123
        or f"= {auth_dept_id}" in query_str  # dept_id = 507
        or f"'{employee_number}'" in query_str  # employee_number = 'A2304013' (v_appr_user_accessible_depts JOIN용)
    )

    if not has_auth_id:
        print(f"[검증 3/5] 실패: 인증된 사용자 ID 미포함 (login_id='{auth_login_id}', user_id={auth_user_id}, dept_id={auth_dept_id}, employee_number='{employee_number}')", file=sys.stderr)
        validation_steps.append(f"   실패: 인증된 사용자의 login_id('{auth_login_id}'), user_id({auth_user_id}), dept_id({auth_dept_id}), employee_number('{employee_number}') 중 하나가 WHERE 조건에 포함되어야 합니다")
        return (
            "\n".join(validation_steps) + "\n\n"
            f"오류: 보안 검증 실패. 본인의 데이터만 조회 가능합니다.\n"
            f"개인 뷰: WHERE login_id = '{auth_login_id}'\n"
            f"부서 뷰: JOIN v_appr_user_accessible_depts a ... WHERE a.employee_number = '{employee_number}'"
        )
    print("[검증 3/5] 통과\n", file=sys.stderr)
    validation_steps.append("   통과")

    # 검증 4: 위험한 SQL 명령어
    validation_steps.append("4단계: 위험 SQL 명령어 스캔")
    print("[검증 4/5] 위험 SQL 명령어 스캔 중...", file=sys.stderr)

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
        print(f"[검증 4/5] 실패: 금지된 SQL 명령어 - {', '.join(found_dangerous)}\n", file=sys.stderr)
        validation_steps.append(f"   실패: 금지된 SQL 명령어 발견 - {', '.join(found_dangerous)}")
        return "\n".join(validation_steps) + f"\n\n오류: 읽기 전용(SELECT)만 허용됩니다. 금지된 명령어: {', '.join(found_dangerous)}"
    print("[검증 4/5] 통과 (읽기 전용 쿼리 확인)\n", file=sys.stderr)
    validation_steps.append("   통과 (읽기 전용 쿼리 확인)")

    # 실제 PostgreSQL 쿼리 실행
    validation_steps.append("5단계: PostgreSQL 쿼리 실행")
    print("[검증 5/5] 쿼리 실행 중...", file=sys.stderr)

    print("\n" + "=" * 80, file=sys.stderr)
    print("[Approval MCP] SQL 쿼리 실행", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(f"쿼리:\n{sql_query}", file=sys.stderr)
    print("=" * 80 + "\n", file=sys.stderr)

    try:
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql_query)

            print(f"[Approval MCP] 쿼리 실행 성공: {len(rows)}건 조회됨\n", file=sys.stderr)

            if not rows:
                validation_steps.append("   결과: 0건")
                return "\n".join(validation_steps) + "\n\n조회된 전자결재 문서가 없습니다.\n\n조건을 변경하거나 기간을 넓혀서 다시 검색해보세요."

            validation_steps.append(f"   성공: {len(rows)}건 조회됨")

            # 첫 번째 행의 컬럼명 확인하여 포맷 결정
            first_row = dict(rows[0])
            has_title = 'title' in first_row

            if has_title and len(rows) <= 30:
                # 결재 문서 목록 포맷팅 (제목 포함 - 번호 형식)
                result_text = "\n".join(validation_steps) + f"\n\n전자결재 조회 결과 ({len(rows)}건)\n\n"

                for idx, row in enumerate(rows, 1):
                    row_dict = dict(row)
                    title = row_dict.pop('title', 'N/A')
                    doc_id = row_dict.pop('doc_id', '')
                    # doc_body는 별도 처리 (HTML → 텍스트 변환 + 길이 제한)
                    doc_body = row_dict.pop('doc_body', None)

                    result_text += f"{idx}. [{title}]\n"
                    if doc_id:
                        result_text += f"   문서ID: {doc_id}\n"

                    for col, val in row_dict.items():
                        if val is not None and str(val).strip():
                            result_text += f"   {col}: {val}\n"

                    if doc_body is not None and str(doc_body).strip():
                        body_text = _truncate_doc_body(str(doc_body))
                        result_text += f"   --- 문서 본문 ---\n{body_text}\n   --- 본문 끝 ---\n"

                    result_text += "\n"
            else:
                # 집계/통계/대량 결과 포맷팅 (테이블 형식)
                result_text = "\n".join(validation_steps) + f"\n\n전자결재 조회 결과 ({len(rows)}건)\n\n"

                # doc_body는 테이블에서 제외 (별도 표시)
                columns = [col for col in first_row.keys() if col != 'doc_body']
                result_text += "| " + " | ".join(str(col) for col in columns) + " |\n"
                result_text += "|" + "|".join("---" for _ in columns) + "|\n"

                for row in rows:
                    row_dict = dict(row)
                    values = [str(row_dict.get(col, '')) for col in columns]
                    result_text += "| " + " | ".join(values) + " |\n"

                # doc_body가 있는 경우 테이블 아래에 본문 별도 표시
                if 'doc_body' in first_row:
                    for idx, row in enumerate(rows, 1):
                        body = row.get('doc_body')
                        if body and str(body).strip():
                            body_text = _truncate_doc_body(str(body))
                            doc_id = row.get('doc_id', f'#{idx}')
                            result_text += f"\n--- 문서 {doc_id} 본문 ---\n{body_text}\n--- 본문 끝 ---\n"

            return result_text.strip()

    except asyncpg.PostgresError as e:
        print(f"[Approval MCP] DB 오류: {str(e)}\n", file=sys.stderr)
        validation_steps.append(f"   DB 오류: {str(e)[:100]}")
        return "\n".join(validation_steps) + f"\n\n데이터베이스 오류: {str(e)}"
    except Exception as e:
        print(f"[Approval MCP] 실행 실패: {str(e)}\n", file=sys.stderr)
        validation_steps.append(f"   실행 실패: {str(e)[:100]}")
        return "\n".join(validation_steps) + f"\n\n쿼리 실행 실패: {str(e)}"


if __name__ == "__main__":
    print("Approval Query MCP Server v1 시작...", file=sys.stderr)
    print("전자결재 문서를 조회합니다.", file=sys.stderr)
    print(f"DB URL: {DATABASE_URL[:30]}...", file=sys.stderr)
    print("", file=sys.stderr)

    mcp.run(transport="stdio")
