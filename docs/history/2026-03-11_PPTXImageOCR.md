# 2026-03-11 PPTX 슬라이드 이미지 OCR

## 개요
PPTX 파일 업로드 시 슬라이드 내 이미지를 Claude Vision API로 OCR 처리하여 텍스트를 추출하도록 개선. 기존에는 텍스트 shape만 추출했으나, 이제 표/차트/그룹shape/이미지까지 모두 처리한다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/services/chromadb_service.py | 수정 | PPTX 텍스트 추출 로직 전면 강화 (표/차트/그룹/이미지 OCR) |

## 상세 내용

### 추가된 헬퍼 메서드

| 메서드 | 역할 |
|--------|------|
| `_extract_table_text(table)` | PPTX 표 → 마크다운 테이블 형식 텍스트 |
| `_extract_chart_text(chart)` | 차트 데이터(제목, 카테고리, 시리즈, 값) 직접 읽기 |
| `_extract_shapes_text_sync(shapes, images_list)` | 재귀적 shape 순회, 이미지 바이트 수집 |

### Shape 처리 로직 (재귀적)
```
각 shape에 대해:
├── has_table → 마크다운 테이블로 변환
├── has_chart → 차트 데이터 직접 추출 (카테고리, 시리즈, 값)
├── GROUP shape → 자식 shapes 재귀 탐색
├── PICTURE shape → image.blob을 리스트에 수집 (10KB 미만 스킵)
└── 그 외 → shape.text 추출 (기존 방식)
```

### 이미지 OCR 처리
- 텍스트/표/차트 추출은 동기적으로 즉시 처리 (API 호출 없음)
- 이미지만 수집 후 `asyncio.gather`로 병렬 Vision API 호출
- 기존 `PDFVisionService.extract_text_from_image()` 재사용
- Semaphore로 동시 호출 제한 (기존 `vision_concurrency` 설정)

### 상수
| 상수 | 값 | 설명 |
|------|-----|------|
| `PPTX_IMAGE_MIN_SIZE_BYTES` | 10KB | 이하 이미지는 로고/아이콘으로 간주하여 OCR 스킵 |
| `PPTX_MAX_IMAGES_PER_FILE` | 20 | 파일당 최대 OCR 대상 이미지 수 (비용 제한) |

### 출력 형식
```
--- 슬라이드 1 ---
(텍스트, 표, 차트 내용)

--- 슬라이드 2 ---
(텍스트, 표, 차트 내용)

[슬라이드 2 이미지 내용]
(Vision API OCR 결과)
```

## 결정 사항 및 주의점
- LibreOffice 방식(PPTX→PDF 변환→전체 렌더링) 대신 python-pptx 직접 추출 방식 채택: 추가 의존성 없이 선별적 Vision API 호출로 비용/성능 최적화
- SmartArt는 python-pptx에서 내부 구조 접근이 제한적이지만, `hasattr(shape, "text")` 폴백으로 최소한의 텍스트 추출 가능
- 외부 링크 이미지(`shape.image.blob` 접근 불가)는 try/except로 스킵
