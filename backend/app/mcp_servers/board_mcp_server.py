"""사내 게시판 검색 MCP 서버

사내 게시판(다우오피스)의 게시글을 검색하는 MCP 서버입니다.
- 목록 검색: v_board_search 뷰
- 본문 조회: v_board_post_detail 뷰 (WHERE post_id = ? 단건 조회)
"""
import sys
import os
import asyncpg
import re
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from fastmcp import FastMCP

mcp = FastMCP("Board Knowledge Base Server v1")


def _fix_post_url(url: str) -> str:
    """DB 뷰의 /posts/ → /post/ URL 보정 (뷰 정의 오타)"""
    return url.replace("/posts/", "/post/") if url else url


def _html_to_text(html: str) -> str:
    """HTML 본문에서 평문 추출"""
    if not html:
        return ""
    text = re.sub(r'<br\s*/?>|</p>|</div>|</li>', '\n', html)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


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
        print("Board DB 연결 풀 생성 완료", file=sys.stderr)
    return _db_pool


def _format_body_result(row_dict: dict, validation_steps: list) -> str:
    """본문 상세 조회 결과 포맷팅"""
    result_text = "\n".join(validation_steps) + "\n\n[게시글 본문]\n\n"

    # 메타 정보
    meta_parts = []
    if row_dict.get('post_title'):
        meta_parts.append(f"제목: {row_dict['post_title']}")
    if row_dict.get('author_name'):
        author_info = row_dict['author_name']
        if row_dict.get('author_dept'):
            author_info += f" ({row_dict['author_dept']})"
        meta_parts.append(f"작성자: {author_info}")
    if row_dict.get('posted_at'):
        meta_parts.append(f"작성일: {str(row_dict['posted_at'])[:10]}")
    if row_dict.get('read_count') is not None:
        meta_parts.append(f"조회수: {row_dict['read_count']}")
    if row_dict.get('post_url'):
        meta_parts.append(f"원문: {_fix_post_url(row_dict['post_url'])}")
    if meta_parts:
        result_text += "\n".join(meta_parts) + "\n\n---\n\n"

    # 본문 텍스트
    body = (row_dict.get('post_body_text') or '').strip()

    # post_body_text가 비어있으면 post_body_html에서 추출
    if not body and row_dict.get('post_body_html'):
        body = _html_to_text(row_dict['post_body_html'])
        if body:
            print(f"[Board MCP] post_body_text 비어있음 → post_body_html에서 추출 ({len(body)}자)",
                  file=sys.stderr)

    if body:
        if len(body) > 3000:
            body = body[:3000] + "\n\n... (본문이 길어 일부만 표시합니다)"
        result_text += body
    else:
        result_text += "(본문 내용을 추출할 수 없습니다. 원문 URL에서 직접 확인해주세요.)"

    return result_text


@mcp.tool()
async def execute_board_query(sql_query: str) -> str:
    """게시판 SQL 실행. SELECT만 허용, v_board_search 뷰 및 v_board_post_detail 뷰 사용."""
    # 쿼리 수신 로그
    print("\n" + "="*80, file=sys.stderr)
    print("[Board MCP] 쿼리 요청 수신", file=sys.stderr)
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
    print("[검증 1/3] SELECT 쿼리 확인 중...", file=sys.stderr)
    if not sql_query.strip().upper().startswith('SELECT'):
        print("[검증 1/3] 실패: SELECT가 아닌 쿼리\n", file=sys.stderr)
        validation_steps.append("   실패: SELECT 쿼리만 허용됩니다")
        return "\n".join(validation_steps) + "\n\n오류: SELECT 쿼리만 실행 가능합니다."
    print("[검증 1/3] 통과\n", file=sys.stderr)
    validation_steps.append("   통과")

    # 검증 2: 허용된 뷰 확인 (v_board_search 또는 v_board_post_detail)
    validation_steps.append("2단계: 대상 뷰 확인")
    print("[검증 2/3] 대상 뷰 확인 중...", file=sys.stderr)
    query_upper = sql_query.upper()
    has_board_search = 'V_BOARD_SEARCH' in query_upper
    has_post_detail = 'V_BOARD_POST_DETAIL' in query_upper
    if not has_board_search and not has_post_detail:
        print("[검증 2/3] 실패: 허용된 뷰 미사용\n", file=sys.stderr)
        validation_steps.append("   실패: v_board_search 또는 v_board_post_detail만 사용 가능합니다")
        return "\n".join(validation_steps) + "\n\n오류: v_board_search 뷰 또는 v_board_post_detail 뷰만 접근 가능합니다.\n가이드의 쿼리 예제를 참고하세요."
    print("[검증 2/3] 통과\n", file=sys.stderr)
    validation_steps.append("   통과")

    # 검증 3: 위험한 SQL 명령어 (단어 경계 체크)
    validation_steps.append("3단계: 위험 SQL 명령어 스캔")
    print("[검증 3/3] 위험 SQL 명령어 스캔 중...", file=sys.stderr)

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
        print(f"[검증 3/3] 실패: 금지된 SQL 명령어 - {', '.join(found_dangerous)}\n", file=sys.stderr)
        validation_steps.append(f"   실패: 금지된 SQL 명령어 발견 - {', '.join(found_dangerous)}")
        return "\n".join(validation_steps) + f"\n\n오류: 읽기 전용(SELECT)만 허용됩니다. 금지된 명령어: {', '.join(found_dangerous)}"
    print("[검증 3/3] 통과 (읽기 전용 쿼리 확인)\n", file=sys.stderr)
    validation_steps.append("   통과 (읽기 전용 쿼리 확인)")

    # 일반 쿼리 실행 (v_board_search, v_board_post_detail 모두 직접 실행)
    validation_steps.append("4단계: PostgreSQL 쿼리 실행")

    print("\n" + "="*80, file=sys.stderr)
    print("[Board MCP] SQL 쿼리 실행", file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"쿼리:\n{sql_query}", file=sys.stderr)
    print("="*80 + "\n", file=sys.stderr)

    try:
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql_query)

            print(f"[Board MCP] 쿼리 실행 성공: {len(rows)}건 조회됨\n", file=sys.stderr)

            if not rows:
                validation_steps.append("   결과: 0건")
                return "\n".join(validation_steps) + "\n\n조회된 게시글이 없습니다.\n\n키워드를 변경하거나 범위를 넓혀서 재검색해보세요.\n(예: '안전보건교육' → '안전교육' 또는 '안전'으로 키워드 분리)"

            validation_steps.append(f"   성공: {len(rows)}건 조회됨")

            # 결과 유형 판별: 본문 조회(post_body_text) vs 목록 검색
            first_row = dict(rows[0])
            is_content_query = 'post_body_text' in first_row

            if is_content_query:
                return _format_body_result(first_row, validation_steps).strip()
            elif 'post_url' in first_row:
                # Step 1: 게시글 목록 검색 결과 (post_url 포함 = 목록 쿼리)
                result_text = "\n".join(validation_steps) + f"\n\n게시판 검색 결과 ({len(rows)}건)\n\n"

                for idx, row in enumerate(rows, 1):
                    row_dict = dict(row)
                    title = row_dict.get('post_title', row_dict.get('title', 'N/A'))
                    board_name = row_dict.get('board_name', '')
                    board_category = row_dict.get('board_category', '')
                    header = row_dict.get('header_name', '')
                    author = row_dict.get('author_name', '')
                    dept = row_dict.get('author_dept', '')
                    posted_at = str(row_dict.get('posted_at', ''))[:10]
                    url = _fix_post_url(row_dict.get('post_url', ''))
                    read_count = row_dict.get('read_count', '')
                    post_id_val = row_dict.get('post_id', '')

                    # 제목 (말머리 포함)
                    display_title = f"{header} {title}" if header else title

                    result_text += f"{idx}. [{display_title}]\n"
                    if board_category:
                        result_text += f"   게시판: {board_category}\n"
                    elif board_name:
                        result_text += f"   게시판: {board_name}\n"
                    if author:
                        author_info = f"{author} ({dept})" if dept else author
                        result_text += f"   작성자: {author_info}\n"
                    if posted_at:
                        result_text += f"   작성일: {posted_at}\n"
                    if read_count:
                        result_text += f"   조회수: {read_count}\n"
                    if post_id_val:
                        result_text += f"   post_id: {post_id_val}\n"
                    if url:
                        result_text += f"   URL: {url}\n"
                    result_text += "\n"
            else:
                # 집계/통계 쿼리 결과 포맷팅 (테이블 형식)
                result_text = "\n".join(validation_steps) + f"\n\n게시판 쿼리 결과 ({len(rows)}건)\n\n"

                columns = list(first_row.keys())
                result_text += "| " + " | ".join(str(col) for col in columns) + " |\n"
                result_text += "|" + "|".join("---" for _ in columns) + "|\n"

                for row in rows:
                    row_dict = dict(row)
                    values = [str(row_dict.get(col, '')) for col in columns]
                    result_text += "| " + " | ".join(values) + " |\n"

            return result_text.strip()

    except asyncpg.PostgresError as e:
        print(f"[Board MCP] DB 오류: {str(e)}\n", file=sys.stderr)
        validation_steps.append(f"   DB 오류: {str(e)[:100]}")
        return "\n".join(validation_steps) + f"\n\n데이터베이스 오류: {str(e)}"
    except Exception as e:
        print(f"[Board MCP] 실행 실패: {str(e)}\n", file=sys.stderr)
        validation_steps.append(f"   실행 실패: {str(e)[:100]}")
        return "\n".join(validation_steps) + f"\n\n쿼리 실행 실패: {str(e)}"


if __name__ == "__main__":
    print("Board Knowledge Base MCP Server v1 시작...", file=sys.stderr)
    print("이 서버는 사내 게시판(다우오피스) 게시글을 검색합니다.", file=sys.stderr)
    print("v_board_search 뷰 + v_board_post_detail 뷰를 통해 조회합니다.", file=sys.stderr)
    print("", file=sys.stderr)

    mcp.run(transport="stdio")
