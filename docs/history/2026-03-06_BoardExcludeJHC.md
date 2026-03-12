# 2026-03-06 게시판 JHC/L&F Plus 제외

## 개요
게시판 검색 및 알림에서 JHC, L&F Plus 게시판을 검색 범위에서 제외하여 L&F 본사 게시판만 조회되도록 변경.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/mcp_servers/board_mcp_server.py | 수정 | SQL 실행 전 JHC/L&F Plus 자동 제외 필터 주입 |
| backend/metadata/MCP_GW_BOARD.md | 수정 | 검색 범위 설명 변경, 게시판 목록에서 제외 표시, JHC 예제 대체 |
| backend/app/services/notice_service.py | 수정 | 알림 공지 쿼리에 L&F Plus 제외 조건 추가 |

## 상세 내용

### MCP 서버 자동 필터 (board_mcp_server.py)
- SQL 검증 3단계 통과 후, 실행 전에 `board_category NOT LIKE 'JHC%' AND board_category NOT LIKE 'L&F Plus%'` 조건 자동 주입
- WHERE 절이 있으면 AND로 추가, 없으면 WHERE 절 생성
- `v_board_post_detail`의 `WHERE post_id = ?` 단건 조회는 필터 미적용 (이미 특정 글 지정)

### 메타데이터 (MCP_GW_BOARD.md)
- 검색 범위 설명에 JHC/L&F Plus 제외 명시
- 게시판 목록에서 해당 항목 취소선 + "검색 제외" 표시
- Case 7 예제: JHC 카테고리 검색 → 말머리 검색으로 대체

### 알림 서비스 (notice_service.py)
- 기존: `board_name NOT LIKE '%JHC%'`만 제외
- 변경: `board_category NOT LIKE 'L&F Plus%'` 조건 추가

## 결정 사항 및 주의점
- `board_category` 기준 필터링: board_name이 아닌 board_category를 사용하여 하위 게시판까지 일괄 제외
- post_id 단건 조회는 필터 미적용: 이미 특정 글을 지정한 경우 회사 구분 없이 조회 허용
