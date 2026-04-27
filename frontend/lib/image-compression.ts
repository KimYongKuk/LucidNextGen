/**
 * 브라우저 사이드 이미지 압축 — 업로드 직전 resize + 재인코딩
 *
 * 목적: HTTP body 크기와 Bedrock vision tokenization 비용을 동시에 줄임.
 * Bedrock 비전 권장 최대 변(=1568px) 이내로 다운샘플하면 시각 정보 손실 거의 없이
 * 파일 크기는 5~10배 작아진다.
 */

const MAX_DIMENSION = 1568;          // longest side cap (Bedrock 비전 권장)
const JPEG_QUALITY = 0.85;            // 시각적으로 거의 무손실 구간
const SKIP_SIZE_BYTES = 800 * 1024;   // 800KB 이하면 그냥 통과

export async function compressImageIfNeeded(file: File): Promise<File> {
  // 애니메이션 GIF는 그대로 — canvas로 그리면 첫 프레임만 남음
  if (file.type === "image/gif") {
    return file;
  }

  // 압축 비대상 (svg, heic 등 브라우저가 못 그리는 포맷)
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    return file;
  }

  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    // 디코딩 실패 시 원본 유지
    return file;
  }

  const longest = Math.max(bitmap.width, bitmap.height);

  // 작고 가벼우면 그대로 (resize 안 해도 OK)
  if (longest <= MAX_DIMENSION && file.size <= SKIP_SIZE_BYTES) {
    bitmap.close();
    return file;
  }

  const scale = longest > MAX_DIMENSION ? MAX_DIMENSION / longest : 1;
  const targetW = Math.round(bitmap.width * scale);
  const targetH = Math.round(bitmap.height * scale);

  const canvas = document.createElement("canvas");
  canvas.width = targetW;
  canvas.height = targetH;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    bitmap.close();
    return file;
  }
  ctx.drawImage(bitmap, 0, 0, targetW, targetH);
  bitmap.close();

  const blob: Blob | null = await new Promise((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY)
  );
  if (!blob || blob.size >= file.size) {
    // 압축이 오히려 커지거나 실패하면 원본 사용
    return file;
  }

  const newName = file.name.replace(/\.[^.]+$/, "") + ".jpg";
  return new File([blob], newName, {
    type: "image/jpeg",
    lastModified: file.lastModified,
  });
}
