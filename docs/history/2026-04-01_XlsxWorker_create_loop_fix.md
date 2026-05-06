# 2026-04-01 XlsxWorker create_workbook 반복 호출 버그 수정

## 개요
XlsxWorker가 `create_workbook`을 반복 호출하고 `write_data_to_excel`로 진행하지 않아 빈 워크북만 생성되는 문제를 수정했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/workers/xlsx_worker.py | 수정 | 시스템 프롬프트 워크플로우 추가, 에러 규칙 개선, 중복 호출 가드 |

## 상세 내용

### 증상
- 운영 로그(11:29, 11:30)에서 동일 패턴 2회 재현
- LLM이 `create_workbook`을 2회 호출 → 성공인데도 "오류가 반복 발생" 응답
- xlsx_output 디렉토리에 4,783 bytes 빈 워크북 다수 누적

### 근본 원인
1. **워크플로우 지침 부재**: create_workbook 후 write_data_to_excel로 진행하라는 명시적 가이드 없음
2. **에러 규칙 #7 오작동**: "같은 도구 2회 실패 시 안내" → LLM이 성공 응답도 "실패"로 오인
3. **DEDUP 혼란**: 2회차 호출 시 파일명이 변경되어 LLM이 에러로 해석

### 수정 내용
1. **워크플로우 섹션 추가**: create_workbook → write_data_to_excel 순서를 명시, "1번만 호출" 강조
2. **에러 규칙 개선**: "Error:"로 시작하는 결과만 에러로 판단하도록 명확화
3. **코드 가드**: `secured_ainvoke`에 `_created_workbook_path` 속성으로 중복 호출 감지, 두 번째 호출 시 write_data_to_excel 안내 메시지 반환

## 결정 사항 및 주의점
- 코드 가드는 `prepare_tools()` 호출 시 매번 새로 생성되므로 요청 간 격리됨
- 기본 시트명 "Sheet" vs "Sheet1" 불일치 존재 (excel-mcp-server의 create_workbook_impl이 "Sheet1"로 생성) — 프롬프트에는 "Sheet"로 안내 중. 향후 확인 필요
