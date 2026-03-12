"use client";

import { useCallback } from "react";

/**
 * 세션 파일 정리 훅 (No-op)
 *
 * 세션 파일은 백엔드 30일 스케줄러가 자동 정리합니다.
 * 프론트엔드에서 즉시 삭제하지 않으므로 세션을 나갔다 돌아와도 파일 맥락이 유지됩니다.
 *
 * @param sessionId - 현재 세션 ID
 * @param hasUploadedFiles - 현재 세션에 업로드된 파일이 있는지 여부
 */
export function useSessionCleanup(
  sessionId: string,
  hasUploadedFiles: boolean
) {
  const markSessionHasFiles = useCallback(() => {
    // UI 상태 추적용 (백엔드 호출 없음)
  }, []);

  return { markSessionHasFiles };
}
