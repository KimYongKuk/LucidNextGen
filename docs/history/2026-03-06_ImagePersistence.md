# 2026-03-06 업로드 이미지 영구 보존

## 개요
채팅 중 업로드한 이미지가 과거 세션에서도 영구적으로 확인 가능하도록 개선. 기존에는 이미지가 base64로 메모리에만 존재하고 `image_count`만 DB에 저장되어 히스토리에서 이미지가 사라지는 문제가 있었음. 이미지 클릭 시 라이트박스로 원본 확인 가능. 파일명에 user_id 포함하여 관리자 추적 용이. 모든 사용자 파일 영구 보존 (자동 삭제 비활성화).

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/api/routes/upload.py` | 수정+추가 | 이미지 디스크 저장, `GET /v1/image/download/{filename}` 엔드포인트 추가 |
| `backend/app/api/routes/chat.py` | 수정 | `ImageData`에 `stored_filename` 필드 추가, metadata에 이미지 참조 저장 |
| `backend/app/services/chat_log_service.py` | 수정 | 히스토리 user 메시지에 이미지 참조 첨부 |
| `backend/app/utils/file_cleanup.py` | 수정 | 모든 사용자 파일 영구 보존 — CLEANUP_TARGETS 비활성화 |
| `frontend/lib/types.ts` | 수정 | `Attachment` 타입에 `storedFilename` 필드 추가 |
| `frontend/components/multimodal-input.tsx` | 수정 | 업로드 응답에서 `stored_filename` 캡처 및 message part 전달 |
| `frontend/hooks/use-simple-chat.ts` | 수정 | `stored_filename`을 백엔드로 전송 |
| `frontend/app/(chat)/api/messages/route.ts` | 수정 | 히스토리 로드 시 이미지 file 파트 복원 |
| `frontend/components/preview-attachment.tsx` | 수정 | 백엔드 URL 이미지를 `<img>` 태그로 렌더링 |

## 상세 내용

### 데이터 흐름
```
[업로드] POST /api/v1/upload/image
  → upload.py: base64 반환 + data/user_uploads/{date}/{user_id}/{uuid}.ext 저장
  → 프론트: data URL 표시 + storedFilename 보관

[메시지 전송]
  → use-simple-chat.ts: {media_type, base64_data, stored_filename}
  → chat.py: Bedrock vision에 base64 사용 (기존 동작 유지)
  → metadata: {images: [{stored_filename, media_type}]} DB 저장

[히스토리 로드]
  → chat_log_service.py: user 메시지에 images[] 첨부
  → messages/route.ts: file 파트로 변환 (url=/api/v1/image/download/...)
  → PreviewAttachment: <img> 태그로 렌더링
```

### 저장 디렉토리
- 경로: `backend/data/user_uploads/{YYYY-MM-DD}/{user_id}/{uuid}.ext`
- 레거시 경로: `backend/data/image_output/` (기존 stored_filename 하위 호환)
- 파일명: `{uuid4}{ext}` (UUID 기반, 충돌 방지)
- 보관 기간: 영구 보존 (CLEANUP_TARGETS 비활성화)
- `stored_filename` 형식: `{date}/{user_id}/{uuid}.ext` (상대 경로)

### 다운로드 엔드포인트
- `GET /api/v1/image/download/{filename}`
- `Cache-Control: public, max-age=31536000, immutable` (UUID 파일명이므로 불변)
- Path traversal 방어 (기존 PDF/PPT 패턴과 동일)

### PreviewAttachment 렌더링
- `data:` URL → Next.js `<Image>` 컴포넌트 (기존 동작 유지)
- 백엔드 URL (`/api/v1/...`) → 일반 `<img>` 태그 (Next.js 이미지 최적화 이슈 방지)

## 결정 사항 및 주의점
- **하위 호환성**: 기존 세션은 metadata에 `images` 필드가 없으므로 이미지 미표시 (현재와 동일)
- **보안**: UUID 기반 파일명으로 추측 불가, path traversal 방어 적용
- **1년 후 파일 삭제 시**: 다운로드 엔드포인트가 404 반환, 이미지 깨짐 (허용 가능)
- **용량**: 이미지 최대 10MB, 기존 PDF/PPT/XLSX와 동일한 보관 정책 적용
