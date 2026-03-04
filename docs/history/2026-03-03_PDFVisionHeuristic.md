# 2026-03-03 PDF Vision 휴리스틱 개선 (이미지 기반 PDF 지원)

## 개요
이미지 기반 PDF (스캔 문서 등) 업로드 시 텍스트 추출이 안 되는 문제를 수정. `process_pdf_page()` 의 분기 로직에서 텍스트가 30자 미만인 페이지는 `is_page_complex()` 결과와 무관하게 Vision API(OCR)를 호출하도록 변경.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/services/pdf_vision_service.py` | 수정 | `process_pdf_page()` 분기 로직 개선 |

## 상세 내용

### 문제 상황
- 이미지로만 구성된 PDF (예: 비밀유지계약서.pdf) 업로드 시 ChromaDB에 "PAGE: 1 / 5" 같은 페이지 번호만 저장됨
- RAG 검색 시 유사도가 낮고 (0.22~0.37) 실제 텍스트 내용이 없어서 LLM이 답변 불가

### 원인
`process_pdf_page()` 의 4가지 분기 중 case 5 (text < 30 AND !complex) 가 Vision API를 건너뜀:
- PyMuPDF의 `page.get_text()`가 이미지 페이지에서 거의 텍스트를 못 뽑음 (< 30자)
- `is_page_complex()`가 순수 이미지 PDF를 "복잡하지 않음"으로 판단 (이미지 메타데이터 감지 실패)
- 결과: Vision API 호출 조건 (`text < 30 AND complex`)을 만족하지 못해 빈 텍스트 그대로 반환

### 수정 내용
**기존 분기 (5가지):**
```
case 1: text >= 100         → text_only (fast path)
case 2: text >= 30, !complex → text_only
case 3: text < 30, complex   → Vision API ✅
case 4: text >= 30, complex  → text_only
case 5: text < 30, !complex  → text_only ← 문제!
```

**수정 후 분기 (4가지):**
```
case 1: text >= 100         → text_only (fast path)
case 2: text >= 30, !complex → text_only
case 3: text < 30            → Vision API ✅ (is_complex 무관)
case 4: text >= 30, complex  → text_only
```

case 3과 case 5를 통합하여, **텍스트가 30자 미만이면 무조건 Vision API 호출**.
Vision API가 텍스트를 못 뽑는 경우에는 원본 텍스트를 fallback으로 사용.

## 결정 사항 및 주의점
- Vision API 호출 빈도가 늘어날 수 있음 (기존에 스킵되던 이미지 페이지들이 이제 호출됨)
- 비용 영향: 이미지 기반 PDF가 자주 업로드되지 않으면 미미. Semaphore(기본 5)로 동시성 제한 유지
- 기존 텍스트 기반 PDF는 영향 없음 (fast path `text >= 100` 에서 처리됨)
