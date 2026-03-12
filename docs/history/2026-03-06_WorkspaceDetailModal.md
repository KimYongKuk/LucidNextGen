# 2026-03-06 워크스페이스 상세 모달

## 개요
관리 대시보드의 상위 워크스페이스 테이블에서 메시지 수/문서 수를 클릭하면 상세 리스트를 볼 수 있도록 모달 팝업 기능을 추가했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/services/report_service.py` | 수정 | `topWorkspaces`에 `workspaceId` 필드 추가, `get_workspace_detail()` 메서드 추가 |
| `backend/app/api/routes/report.py` | 수정 | `GET /workspaces/detail` 엔드포인트 추가 |
| `frontend/lib/api/report.ts` | 수정 | `WorkspaceDetailData` 타입 + `getWorkspaceDetail` API 메서드 추가 |
| `frontend/components/dashboard/workspace-detail-modal.tsx` | 추가 | 메시지/문서 탭 전환 모달 컴포넌트 |
| `frontend/components/dashboard/workspace-usage.tsx` | 수정 | 메시지 수/문서 수를 클릭 가능한 버튼으로 변경 |
| `frontend/app/admin/report/page.tsx` | 수정 | 워크스페이스 상세 모달 상태 관리 및 렌더링 |

## 상세 내용

### 백엔드 API
- **엔드포인트**: `GET /api/v1/admin/report/workspaces/detail`
- **파라미터**: `date_from`, `date_to`, `workspace_id`, `tab` (messages | documents)
- **메시지 탭**: `chat_log_new` JOIN `chat_sessions`로 해당 워크스페이스의 메시지 50건 조회 (최신순)
- **문서 탭**: ChromaDB `workspace_{uuid}` 컬렉션에서 고유 파일 목록 + 청크 수 조회

### 프론트엔드 모달
- 기존 `UserDetailModal` 패턴을 따름 (일관된 UX)
- 탭 전환 시 API 재호출 (탭별 독립 데이터)
- 메시지 탭: 일시, 질문, 답변 미리보기, 기능(인텐트), 응답시간 표시
- 문서 탭: 파일명, 유형(색상 뱃지), 청크 수 표시
- 파일 유형별 컬러: PDF(빨강), DOCX(파랑), XLSX(초록), PPTX(주황)

### 클릭 인터랙션
- 메시지 수 클릭 → 모달 열림 (메시지 탭 활성)
- 문서 수 클릭 → 모달 열림 (문서 탭 활성)
- 숫자가 파란색으로 표시되어 클릭 가능함을 시각적으로 표시
- hover 시 밑줄 + 배경색 변경

## 결정 사항 및 주의점
- `topWorkspaces` 응답에 `workspaceId` 필드를 추가하여 프론트엔드에서 상세 API 호출 시 활용
- 문서 탭은 ChromaDB에서 직접 조회하므로 날짜 범위와 무관 (워크스페이스 전체 문서 표시)
