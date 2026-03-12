# 2026-03-10 PDF/DOCX 인라인 미리보기

## 개요
생성된 PDF, DOCX 파일을 다운로드 없이 채팅 화면 오른쪽 패널에서 바로 미리보기할 수 있는 기능 추가. 기존 XLSX 미리보기(Univer)와 동일한 UX 패턴 적용.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `frontend/hooks/use-document-viewer.ts` | 신규 | PDF/DOCX 통합 뷰어 상태 관리 훅 (SWR 기반) |
| `frontend/components/pdf-viewer.tsx` | 신규 | PDF 뷰어 — 브라우저 내장 PDF 렌더러 (iframe) |
| `frontend/components/docx-viewer.tsx` | 신규 | DOCX 뷰어 — docx-preview 라이브러리로 HTML 변환 렌더링 |
| `frontend/components/document-viewer-panel.tsx` | 신규 | 문서 타입별 뷰어 분기 래퍼 (dynamic import, SSR 비활성화) |
| `frontend/components/elements/response.tsx` | 수정 | PDF/DOCX 다운로드 링크에 미리보기(Eye) 버튼 추가 |
| `frontend/components/chat.tsx` | 수정 | DocumentViewerPanel 통합, 세션 전환 시 뷰어 cleanup |
| `frontend/app/globals.css` | 수정 | docx-preview 렌더링 스타일 (페이지 그림자, 다크모드) |
| `frontend/package.json` | 수정 | docx-preview@0.3.7 의존성 추가 |
| `backend/app/api/routes/upload.py` | 수정 | PDF 다운로드 엔드포인트에 `inline` 쿼리 파라미터 추가 |

## 상세 내용

### 아키텍처
```
[응답 메시지] → PDFDownloadLink / DocxDownloadLink
  ├── Eye 아이콘 클릭 → useDocumentViewer.openFile(filename, "pdf"|"docx")
  └── FileDown 아이콘 → 기존 다운로드 링크
        ↓
[chat.tsx] PanelGroup
  ├── Chat Panel (리사이즈 가능)
  └── DocumentViewerPanel (오른쪽 50%)
        ├── PdfViewer (iframe)
        └── DocxViewer (docx-preview)
```

### PDF 미리보기
- **방식**: `<iframe src="/api/v1/pdf/download/{filename}?inline=true" />` — 브라우저 내장 PDF 뷰어
- **핵심**: 백엔드 `Content-Disposition: inline` (기본은 `attachment` → 다운로드됨)
- **장점**: 추가 라이브러리 불필요, 확대/축소/페이지 이동 기본 제공
- **제약**: 브라우저별 PDF 뷰어 UI 차이 (Chrome vs Firefox vs Edge)

### DOCX 미리보기
- **라이브러리**: `docx-preview@0.3.7` (npm)
- **방식**: DOCX 파일을 fetch → Blob → `renderAsync(blob, container)` → HTML 변환 렌더링
- **옵션**: breakPages, ignoreWidth=true (패널 폭에 맞춤), renderHeaders/Footers/Footnotes/Endnotes
- **레이아웃**: `ignoreWidth: true` + CSS `max-width: 100%` → 패널 크기에 반응형 적용
- **다크모드**: CSS 변수 기반 배경/텍스트 색상 전환
- **제약**: 복잡한 Word 서식(SmartArt, 고급 차트 등)은 미지원

### 상태 관리
- `use-document-viewer.ts`: SWR 기반 전역 상태 (`document-viewer` 키)
- `DocumentViewerState`: `{ isOpen, filename, documentType, isLoading }`
- XLSX 뷰어와 독립적 — 동시에 열리면 XLSX 우선 표시

### 뷰어 우선순위
- XLSX 뷰어가 열려 있으면 → XLSX 표시 (기존 동작 유지)
- XLSX 닫혀 있고 Document 뷰어 열려 있으면 → PDF/DOCX 표시
- 세션 전환 시 → 모든 뷰어 자동 닫힘

## 결정 사항 및 주의점
- **PDF는 iframe 방식 채택**: react-pdf(pdf.js)보다 간단하고 브라우저 네이티브 기능(인쇄, 텍스트 선택) 활용 가능
- **DOCX는 docx-preview 채택**: 서버 LibreOffice 설치 불필요, 우리가 python-docx로 생성한 단순한 DOCX에 충분
- **PPT 미리보기는 미구현**: 브라우저에서 렌더링할 좋은 라이브러리 없음, LibreOffice headless 필요
- **docx-preview 설치 시 `--legacy-peer-deps` 필요**: peer dependency 충돌
