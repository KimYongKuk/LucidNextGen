# 2026-04-14 공유 도구(PDF/DOCX/차트) BaseWorker 기본값 승격

## 개요
VisualizationWorker 제거 후 4개 워커에만 개별 override했던 shared_tool_names(PDF/DOCX/차트)를 BaseWorker 기본값으로 승격하여 모든 워커에서 문서 생성 가능하도록 수정.

## 배경
- b27c8be(3/23) 리팩토링에서 VisualizationWorker를 제거하고 shared_tool_names로 분배
- Direct, WebSearch, UserFiles, CorpRAG 4개만 override → 나머지 워커(Xlsx, Mail, Approval 등)에서 문서 생성 불가
- XlsxWorker로 라우팅된 상태에서 "워드로 만들어줘" 요청 시 "Excel만 가능합니다" 응답 반복
- DirectResponseWorker의 시스템 프롬프트에 도구 사용 지시 누락 (도구가 바인딩되어 있으나 LLM이 호출 안 함)

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/workers/base_worker.py | 수정 | shared_tool_names 기본값: [] → 공유 도구 리스트, ARCHIVABLE_TOOLS에 create_document_docx 추가 |
| backend/app/agents/workers/direct_worker.py | 수정 | 시스템 프롬프트에 문서/차트 생성 도구 안내 추가, shared_tool_names를 base + search_workspace_docs로 변경 |
| backend/app/agents/workers/web_search_worker.py | 수정 | 중복 shared_tool_names override 제거 (base 상속) |
| backend/app/agents/workers/user_files_worker.py | 수정 | 중복 shared_tool_names override 제거 (base 상속) |
| backend/app/agents/workers/corp_rag_worker.py | 수정 | 중복 shared_tool_names override 제거 (base 상속) |
| backend/app/agents/workers/xlsx_worker.py | 수정 | 시스템 프롬프트에 공유 도구(PDF/DOCX) 안내 추가 |
| backend/app/agents/intent_classifier.py | 수정 | 잘못 추가된 quick_classify 규칙 원복 |

## 상세 내용

### 아키텍처 변경
- **Before**: opt-in 방식 — 4개 워커만 shared_tool_names override
- **After**: opt-out 방식 — BaseWorker 기본값에 공유 도구 포함, 불필요한 워커에서 빈 리스트로 override

### BaseWorker.shared_tool_names 기본값
```python
["create_line_chart", "create_bar_chart", "create_pie_chart", "create_multi_chart",
 "create_document_pdf", "create_table_spec_pdf", "create_document_docx"]
```

### 시스템 프롬프트 수정
- DirectResponseWorker: "도구가 필요 없는 작업" 문구 제거, PDF/DOCX/차트 도구 사용 지침 명시
- XlsxWorker: "다른 형식 문서 생성" 섹션 추가 (Excel 전용이라는 제한 해제)

## 결정 사항 및 주의점
- 자체 build_system_prompt를 가진 워커(XlsxWorker, PPTWorker 등)는 base의 공유 도구 안내 섹션을 자동으로 타지 않으므로 별도 추가 필요
- PPTWorker는 차트 도구가 이미 tool_names에 있어 중복되지만 filter_tools가 합집합으로 처리하므로 문제 없음
