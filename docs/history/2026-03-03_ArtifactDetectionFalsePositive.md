# 2026-03-03 파일 아티팩트 감지 False Positive 수정

## 개요
비-엑셀 워커(IT지원 등)의 응답에서 `.xlsx`, `.pptx`, `.pdf` 파일명이 언급되면 엑셀 프리뷰/다운로드 링크가 잘못 렌더링되는 문제를 수정. 백엔드의 `intent_classified` SSE 이벤트에서 워커 이름을 캡처하여 프론트엔드에서 조건부로 아티팩트 감지를 실행하도록 개선.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `frontend/hooks/use-simple-chat.ts` | 수정 | `intent_classified` 이벤트에서 `workerName` 캡처, `<!--WORKER:name-->` 마커를 메시지에 삽입 |
| `frontend/components/elements/response.tsx` | 수정 | `processPDFContent`, `processPPTContent`, `processXLSXContent`에 workerName 파라미터 추가, 광범위 패턴(1,2) 조건부 실행 |

## 상세 내용

### 문제 원인
`response.tsx`의 파일 아티팩트 감지 함수(`processPDFContent`, `processPPTContent`, `processXLSXContent`)가 4가지 패턴으로 파일명을 추출:
- **패턴 1**: `파일명: xxx.xlsx` (광범위)
- **패턴 2**: `파일: xxx.xlsx` (광범위)
- **패턴 3**: `xlsx_output/xxx.xlsx` (경로 기반, 구체적)
- **패턴 4**: `C:\...\xlsx_output\xxx.xlsx` (전체 경로, 구체적)

패턴 1, 2가 너무 광범위하여 IT지원 워커가 "해당 **파일**: report.xlsx" 형태로 응답하면 다운로드 링크가 생성됨.

### 해결 방안
**워커 이름 기반 조건부 감지**:

1. `use-simple-chat.ts`: 백엔드에서 이미 전송하는 `intent_classified` SSE 이벤트에서 `workerName`을 캡처하여 완료 시 `<!--WORKER:worker_name-->` HTML 코멘트 마커를 콘텐츠 앞에 삽입

2. `response.tsx`: 마커를 파싱하여 각 process 함수에 전달
   - `workerName`이 해당 워커(`xlsx_worker`, `ppt_worker`, `visualization_worker`)일 때 → 패턴 1~4 모두 활성
   - `workerName`이 다른 워커일 때 → 패턴 3, 4만 활성 (경로 기반, false positive 없음)
   - `workerName`이 없을 때 (기존 메시지/히스토리) → 모든 패턴 활성 (하위 호환)

### 워커-패턴 매핑
| 파일 유형 | 허용 워커 | 광범위 패턴 활성 조건 |
|-----------|-----------|----------------------|
| PDF (.pdf) | `visualization_worker` | workerName 없음 OR `visualization_worker` |
| PPT (.pptx) | `ppt_worker` | workerName 없음 OR `ppt_worker` |
| XLSX (.xlsx) | `xlsx_worker` | workerName 없음 OR `xlsx_worker` |

## 결정 사항 및 주의점
- **하위 호환**: DB에서 로드된 기존 메시지에는 `<!--WORKER:-->` 마커가 없으므로 모든 패턴이 활성화됨 (기존 동작 유지)
- **백엔드 변경 없음**: `intent_classified` 이벤트는 이미 프론트엔드로 전송되고 있었으나 미활용 상태였음
- **경로 기반 패턴(3, 4)은 항상 활성**: `xlsx_output/`, `ppt_output/`, `pdf_output/` 경로는 해당 워커만 생성하므로 false positive 위험 없음
- 스트리밍 중에는 마커 미삽입 (완료 시점에만), 따라서 스트리밍 UI에 영향 없음
