# 2026-03-18 Tool Call 태그 스트리밍 필터링

## 개요
웹 검색 등 도구 사용 시 LLM이 `<tool_call>`, `<tool_response>` 태그를 텍스트로 출력하면 사용자에게 raw 코드가 그대로 노출되는 문제를 수정. 상태 기반 스트리밍 필터링으로 해당 태그를 실시간 제거.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/a2a_streaming.py | 수정 | 상태 기반 tool_call/tool_response 태그 필터링 추가 |
| frontend/lib/utils.ts | 수정 | sanitizeText()에 tool 태그 regex 안전장치 추가 |

## 상세 내용

### 문제
- AWS Bedrock 모델이 간헐적으로 tool_use API 대신 `<tool_call>` XML 텍스트를 생성
- 기존 코드는 `<search>` 태그만 제거하고 tool 관련 태그는 미처리
- 스트리밍 특성상 태그가 여러 청크에 걸쳐 오므로 단순 regex 불가

### 해결: 상태 기반 문자 단위 필터링
- `_inside_tool_tag` (bool): 현재 tool 태그 내부인지 추적
- `_tag_buffer` (str): 부분 태그 감지용 버퍼
- 문자 단위로 처리하며 시작 태그 감지 시 내부 콘텐츠 전부 버림
- 종료 태그 감지 시 정상 출력 복귀
- `collected_response` (DB 저장용)에도 최종 regex 정리 추가

### 프론트엔드 안전장치
- `sanitizeText()`에 `<tool_call>`, `<tool_response>` regex 추가
- 백엔드 필터링 우회 시 최종 방어선

## 결정 사항 및 주의점
- 버퍼 크기 20자 제한: `<tool_response>`가 15자이므로 여유 있게 설정
- `<` 미포함 시 즉시 flush하여 일반 텍스트 지연 최소화
