"""회계/재경 VOC Knowledge Base MCP 서버

회계/재경 지원요청 해결 사례를 검색하는 MCP 서버입니다.
v_works_app_1320_data 뷰를 통해 과거 해결 사례를 조회합니다.

참고: LFON은 사내 그룹웨어 시스템명입니다.
"""
import sys
import os
import asyncpg
import re
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastmcp import FastMCP

mcp = FastMCP("Accounting VOC Knowledge Base Server v1")

# PostgreSQL 연결 정보 (TIMS DB)
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
        print("회계 VOC DB 연결 풀 생성 완료", file=sys.stderr)
    return _db_pool


@mcp.tool()
async def execute_acct_voc_query(sql_query: str) -> str:
    """회계 VOC SQL 실행. SELECT만 허용, v_works_app_1320_data 뷰 사용."""
    # 쿼리 수신 로그
    print("\n" + "="*80, file=sys.stderr)
    print("[ACCT VOC MCP] 쿼리 요청 수신", file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"받은 쿼리:\n{sql_query}", file=sys.stderr)
    print("="*80 + "\n", file=sys.stderr)

    validation_steps = []  # 검증 과정 기록

    # 실행된 쿼리 기록 (디버깅용)
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

    # 검증 2: v_works_app_1320_data 뷰 확인
    validation_steps.append("2단계: 대상 뷰 확인")
    print("[검증 2/4] 대상 뷰 확인 중...", file=sys.stderr)
    query_upper = sql_query.upper()
    if 'V_WORKS_APP_1320_DATA' not in query_upper:
        print("[검증 2/4] 실패: v_works_app_1320_data 뷰 미사용\n", file=sys.stderr)
        validation_steps.append("   실패: v_works_app_1320_data 뷰를 사용해야 합니다")
        return "\n".join(validation_steps) + "\n\n오류: v_works_app_1320_data 뷰만 접근 가능합니다.\n가이드의 쿼리 예제를 참고하세요."
    print("[검증 2/4] 통과\n", file=sys.stderr)
    validation_steps.append("   통과")

    # 검증 3: 답변내용 IS NOT NULL 권장 (경고만, 차단 안함)
    validation_steps.append("3단계: 답변내용 필터 확인")
    print("[검증 3/4] 답변내용 필터 확인 중...", file=sys.stderr)
    if '답변내용' not in sql_query or 'IS NOT NULL' not in query_upper:
        print("[검증 3/4] 경고: 답변내용 IS NOT NULL 조건 누락\n", file=sys.stderr)
        validation_steps.append("   경고: 답변내용 IS NOT NULL 조건을 추가하면 답변 완료된 건만 조회됩니다")
    else:
        print("[검증 3/4] 통과\n", file=sys.stderr)
        validation_steps.append("   통과")

    # 검증 4: 위험한 SQL 명령어 (단어 경계 체크)
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
    print("[ACCT VOC MCP] SQL 쿼리 실행", file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"쿼리:\n{sql_query}", file=sys.stderr)
    print("="*80 + "\n", file=sys.stderr)

    try:
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql_query)

            print(f"[ACCT VOC MCP] 쿼리 실행 성공: {len(rows)}건 조회됨\n", file=sys.stderr)

            if not rows:
                validation_steps.append("   결과: 0건")
                return "\n".join(validation_steps) + "\n\n조회된 회계/재경 VOC 사례가 없습니다.\n\n키워드를 분리하거나 유의어로 변경하여 재검색해보세요.\n(예: '세금계산서 오류' -> '세금계산서' or '발행' or '전표')"

            validation_steps.append(f"   성공: {len(rows)}건 조회됨")

            # 첫 번째 행의 컬럼명 확인하여 쿼리 유형 판단
            first_row = dict(rows[0])
            is_voc_search = '제목' in first_row

            if is_voc_search:
                # VOC 검색 결과 포맷팅 (기존 로직)
                result_text = "\n".join(validation_steps) + f"\n\n회계/재경 VOC 검색 결과 ({len(rows)}건)\n\n"

                for idx, row in enumerate(rows, 1):
                    row_dict = dict(row)

                    # 주요 필드 추출 (회계 VOC 스키마에 맞게)
                    title = row_dict.get('제목', 'N/A')
                    inquiry_detail = row_dict.get('문의상세내용', '')
                    answer = row_dict.get('답변내용', '')
                    created_at = str(row_dict.get('등록일', 'N/A'))
                    category = row_dict.get('문의구분', '')
                    status = row_dict.get('상태', '')
                    assignee = row_dict.get('처리담당자', '')
                    requester = row_dict.get('요청자명', '')
                    company = row_dict.get('소속법인', '')

                    # 포맷팅
                    result_text += f"{idx}. [{title}]\n"
                    result_text += f"   등록일: {created_at}\n"

                    if category:
                        result_text += f"   문의구분: {category}\n"

                    if status:
                        result_text += f"   상태: {status}\n"

                    if company:
                        result_text += f"   소속법인: {company}\n"

                    if inquiry_detail:
                        # 상세 내용이 너무 길면 축약
                        if len(inquiry_detail) > 150:
                            inquiry_detail = inquiry_detail[:150] + "..."
                        result_text += f"   문의: {inquiry_detail}\n"

                    if answer:
                        # 답변내용이 너무 길면 축약
                        if len(answer) > 300:
                            answer = answer[:300] + "..."
                        result_text += f"   답변: {answer}\n"

                    if assignee:
                        result_text += f"   담당자: {assignee}\n"

                    result_text += "\n"
            else:
                # 집계/통계 쿼리 결과 포맷팅 (테이블 형식)
                result_text = "\n".join(validation_steps) + f"\n\n회계/재경 VOC 쿼리 결과 ({len(rows)}건)\n\n"

                # 컬럼명 추출
                columns = list(first_row.keys())
                result_text += "| " + " | ".join(str(col) for col in columns) + " |\n"
                result_text += "|" + "|".join("---" for _ in columns) + "|\n"

                # 데이터 행
                for row in rows:
                    row_dict = dict(row)
                    values = [str(row_dict.get(col, '')) for col in columns]
                    result_text += "| " + " | ".join(values) + " |\n"

            return result_text.strip()

    except asyncpg.PostgresError as e:
        print(f"[ACCT VOC MCP] DB 오류: {str(e)}\n", file=sys.stderr)
        validation_steps.append(f"   DB 오류: {str(e)[:100]}")
        return "\n".join(validation_steps) + f"\n\n데이터베이스 오류: {str(e)}"
    except Exception as e:
        print(f"[ACCT VOC MCP] 실행 실패: {str(e)}\n", file=sys.stderr)
        validation_steps.append(f"   실행 실패: {str(e)[:100]}")
        return "\n".join(validation_steps) + f"\n\n쿼리 실행 실패: {str(e)}"


if __name__ == "__main__":
    print("Accounting VOC Knowledge Base MCP Server v1 시작...", file=sys.stderr)
    print("이 서버는 회계/재경 지원요청 해결 사례를 검색합니다.", file=sys.stderr)
    print("v_works_app_1320_data 뷰를 통해 과거 VOC를 조회합니다.", file=sys.stderr)
    print("", file=sys.stderr)

    mcp.run(transport="stdio")
