# 2026-03-04 생성형 Worker 웹검색 도구 추가

## 개요
PPTWorker, XlsxWorker, VisualizationWorker에 `tavily_search` 도구를 추가하여, 시장 현황/트렌드/통계 등 최신 정보가 필요한 생성 요청 시 웹검색을 먼저 수행한 뒤 결과물을 생성하도록 개선.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/workers/ppt_worker.py | 수정 | tool_names에 tavily_search 추가, TOOLS 섹션에 Web Search 항목 추가, 워크플로우에 웹검색 판단 단계(2단계) 삽입 |
| backend/app/agents/workers/xlsx_worker.py | 수정 | tool_names에 tavily_search 추가, 시스템 프롬프트에 "웹 검색" 섹션 추가 (데이터 직접 제공 시 스킵 안내 포함) |
| backend/app/agents/workers/visualization_worker.py | 수정 | tool_names에 tavily_search 추가, TOOLS에 Web Search 항목 추가, PDF WORKFLOW에 검색 단계 삽입 |

## 상세 내용

### 배경
기존에는 "2차전지 시장 현황 PPT 5장으로 만들어줘" 같은 요청이 들어오면, PPTWorker가 LLM 학습 데이터(knowledge cutoff)에만 의존하여 부정확하거나 오래된 정보로 PPT를 생성했음. 엑셀/PDF도 동일한 문제.

### 변경 내용
3개 생성형 Worker에 `tavily_search` 도구를 추가하고, 시스템 프롬프트에 "최신 정보가 필요한 주제인지 먼저 판단 → 해당되면 웹검색 수행 → 결과 반영" 워크플로우를 명시.

**웹검색이 트리거되는 주제 유형:**
- 시장 현황/동향, 트렌드, 산업 분석
- 기술 전망, 경쟁사 분석
- 통계/수치 데이터

**웹검색이 스킵되는 경우:**
- 사용자가 직접 데이터를 제공한 경우
- 기존 파일 수정 요청
- 대화 내 이미 충분한 데이터가 있는 경우

### Worker별 도구 현황 (변경 후)
| Worker | 기존 도구 | 추가 도구 |
|--------|----------|-----------|
| PPTWorker | PPT 3개 + 차트 4개 + 파일검색 2개 | tavily_search |
| XlsxWorker | Excel 24개 | tavily_search |
| VisualizationWorker | PDF 3개 + 차트 4개 + 파일검색 2개 | tavily_search |

## 결정 사항 및 주의점
- **1안(도구 추가) 채택**: 오케스트레이터 레벨의 Worker 체이닝(2안)은 아키텍처 변경이 크므로 추후 검토
- tavily_search는 MCP 서버(`tavily-mcp`)에서 제공하므로 별도 설정 불필요 — 기존 WebSearchWorker가 사용하던 도구를 공유
- 웹검색 추가로 Worker의 agent step이 늘어날 수 있으나, 기존 max_agent_steps로 충분할 것으로 판단 (검색 1~2회 추가)
