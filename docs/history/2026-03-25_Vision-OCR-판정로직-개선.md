# 2026-03-25 Vision OCR 판정 로직 개선 + PPTX media_type 버그 수정

## 개요
PDF 업로드 시 Vision OCR 호출 판정 로직의 사각지대 2건 수정, PPTX 이미지 OCR이 운영에서 조용히 실패하던 media_type 버그 수정, 임베딩 모델 로드 안정화.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/services/pdf_vision_service.py | 수정 | is_page_complex 이미지 면적 판정 추가, 빈 페이지 Vision 스킵, media_type 자동 감지 |
| backend/app/services/chromadb_service.py | 수정 | PPTX 이미지 해시 중복 제거, low_cpu_mem_usage=True |

## 상세 내용

### 1. PDF Vision OCR 판정 로직 개선 (pdf_vision_service.py)

**기존 문제 — 사각지대 2건:**

| 케이스 | 기존 동작 | 문제 |
|--------|----------|------|
| 텍스트 30~99자 + 큰 스크린샷 이미지 + 드로잉 없음 | Vision 스킵 | 이미지 내용 임베딩 누락 |
| 텍스트 < 30자 + 이미지 없음 (빈 페이지) | Vision 호출 | 불필요한 API 비용 (~15초/건) |

**기존 분기 로직:**
```
텍스트 ≥ 100자 → fast-path (스킵)
텍스트 30~99자 → complex_drawings > 30 이면 Vision, 아니면 스킵
텍스트 < 30자  → 무조건 Vision
```

**개선 후:**
```
텍스트 ≥ 100자 → fast-path (스킵) — 변경 없음
텍스트 < 100자 →
  ① 큰 이미지(페이지 20%+) 있음 → Vision (NEW)
  ② 의미 있는 이미지 + complex_drawings > 30 → Vision
  ③ complex_drawings > 100 → Vision
  ④ 텍스트 < 30자 + 이미지 있음 → Vision
  ⑤ 텍스트 < 30자 + 이미지 없음 → 스킵 (NEW)
  ⑥ 그 외 → 텍스트만
```

**`is_page_complex()` 변경:**
- `has_large_image` 플래그 추가: 페이지 면적의 20% 이상 차지하는 이미지 감지
- 기존 조건(`significant_images > 0 and complex_drawings > 30`)에 `has_large_image` OR 조건 추가
- 스크린샷이 붙은 매뉴얼 페이지도 complex로 판정되어 Vision OCR 대상에 포함

**`process_pdf_page()` 변경:**
- 텍스트 < 30자 분기에 `has_images` 체크 추가
- 이미지가 없는 빈 페이지("- 끝 -", 구분선 등)는 Vision API 호출하지 않음

### 2. PPTX media_type 버그 수정 (pdf_vision_service.py)

**원인:** `extract_text_from_image()`에서 media_type을 `"image/jpeg"`로 하드코딩.
PDF 경로에서는 JPEG 변환 후 전송하므로 문제없으나, PPTX 경로에서는 `shape.image.blob`이 PNG 원본 그대로 전달됨.
PNG 이미지를 `image/jpeg`로 Bedrock에 보내면 ValidationException이 발생하고, `return_exceptions=True`로 에러가 조용히 무시됨.

**결과:** 운영서버에서 PPTX 이미지 OCR이 사실상 전혀 동작하지 않고 있었음 (에러가 0.6초 만에 반환되어 빨라 보였을 뿐).

**수정:** `_detect_media_type()` 메서드 추가 — 매직바이트 기반으로 PNG/JPEG/GIF/WEBP 자동 감지.

### 3. PPTX 이미지 해시 중복 제거 (chromadb_service.py)

PPT 템플릿의 로고/배경 이미지가 매 슬라이드마다 반복되어 동일 이미지가 여러 번 OCR 대상에 포함되는 문제.
MD5 해시 기반 중복 제거 + 파일 전체 기준 PPTX_MAX_IMAGES_PER_FILE(20) 제한 적용.

### 4. 임베딩 모델 로드 안정화 (chromadb_service.py)

`low_cpu_mem_usage=True` 설정 추가. Windows 환경에서 safetensors의 mmap이 커밋 차지 한도를 초과하여 프로세스가 강제 종료되는 문제 방지.

## 결정 사항 및 주의점

- **Vision OCR 속도**: Bedrock Sonnet Vision은 복잡한 이미지당 ~15초 소요. 리전(서울/버지니아) 변경으로는 개선 불가. 모델 추론 자체가 병목.
- **Haiku 대안 불가**: 한글 OCR 정확도가 심각하게 떨어짐 ("회계팀"→"최계팀", "수정"→"주정")
- **Textract 대안 불가**: 한글 인식 품질이 사용 불가 수준 ("구시제조팀"→"KΓ")
- **향후 개선**: 한글 지원이 우수한 OCR 전용 서비스가 나오면 교체 검토
- **운영 배포 시**: media_type 수정이 포함되어 PPTX OCR이 처음으로 정상 동작하게 됨 → 기존에 없던 Vision API 호출이 발생하므로 비용/속도 모니터링 필요
