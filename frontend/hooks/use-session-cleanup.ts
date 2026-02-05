"use client";

import { useEffect, useRef, useCallback } from "react";

/**
 * 세션 파일 자동 정리 훅
 *
 * 세션 전환, 브라우저 닫기/새로고침 시 업로드된 임시 파일을 자동으로 정리합니다.
 *
 * @param sessionId - 현재 세션 ID
 * @param hasUploadedFiles - 현재 세션에 업로드된 파일이 있는지 여부
 */
export function useSessionCleanup(
  sessionId: string,
  hasUploadedFiles: boolean
) {
  const previousSessionIdRef = useRef<string | null>(null);
  const hasFilesRef = useRef(false);

  // 파일 업로드 상태 추적 (ref와 localStorage 동기화)
  useEffect(() => {
    hasFilesRef.current = hasUploadedFiles;
    if (hasUploadedFiles && sessionId) {
      localStorage.setItem(`session_files_${sessionId}`, "true");
    }
  }, [hasUploadedFiles, sessionId]);

  // 세션 정리 함수
  const cleanupSession = useCallback((targetSessionId: string) => {
    try {
      // keepalive: true로 페이지 언로드 시에도 요청 완료 보장
      fetch(`/api/v1/upload/session/${targetSessionId}/cleanup`, {
        method: "POST",
        keepalive: true,
      }).catch((err) => {
        console.warn(`Session cleanup failed for ${targetSessionId}:`, err);
      });
    } catch (err) {
      console.warn(`Session cleanup error for ${targetSessionId}:`, err);
    }
  }, []);

  // 세션 전환 시 이전 세션 정리
  useEffect(() => {
    const previousId = previousSessionIdRef.current;

    // 이전 세션이 있고, 현재 세션과 다른 경우
    if (previousId && previousId !== sessionId) {
      const hadFiles = localStorage.getItem(`session_files_${previousId}`);
      if (hadFiles) {
        console.log(`Cleaning up previous session: ${previousId}`);
        cleanupSession(previousId);
        localStorage.removeItem(`session_files_${previousId}`);
      }
    }

    previousSessionIdRef.current = sessionId;
  }, [sessionId, cleanupSession]);

  // 브라우저 닫기/새로고침 시 정리
  useEffect(() => {
    const handleUnload = () => {
      // 현재 세션에 파일이 있는 경우에만 정리
      const hadFiles = localStorage.getItem(`session_files_${sessionId}`);
      if (hadFiles && sessionId) {
        // sendBeacon은 페이지 언로드 시에도 안정적으로 요청 전송
        const success = navigator.sendBeacon(
          `/api/v1/upload/session/${sessionId}/cleanup`
        );
        if (success) {
          localStorage.removeItem(`session_files_${sessionId}`);
        }
        console.log(`Session cleanup beacon sent: ${sessionId}, success=${success}`);
      }
    };

    // pagehide는 모바일에서 더 안정적, beforeunload는 데스크톱 호환성
    window.addEventListener("pagehide", handleUnload);
    window.addEventListener("beforeunload", handleUnload);

    return () => {
      window.removeEventListener("pagehide", handleUnload);
      window.removeEventListener("beforeunload", handleUnload);
    };
  }, [sessionId]);

  // 수동으로 파일 업로드 표시 (MultimodalInput에서 호출)
  const markSessionHasFiles = useCallback(() => {
    if (sessionId) {
      localStorage.setItem(`session_files_${sessionId}`, "true");
      hasFilesRef.current = true;
    }
  }, [sessionId]);

  return { markSessionHasFiles };
}
