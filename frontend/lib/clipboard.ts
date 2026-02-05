/**
 * 클립보드 복사 유틸리티
 *
 * HTTPS 환경과 HTTP 환경 모두에서 작동하는 클립보드 복사 기능을 제공합니다.
 *
 * @description
 * - HTTPS/localhost: navigator.clipboard API 사용 (최신 브라우저 표준)
 * - HTTP (외부 접근): document.execCommand('copy') fallback 사용 (레거시 방식)
 *
 * @author LF Chatbot Team
 */

/**
 * 텍스트를 클립보드에 복사합니다.
 *
 * 동작 방식:
 * 1. 먼저 Clipboard API (navigator.clipboard.writeText)를 시도합니다.
 *    - HTTPS 또는 localhost에서만 작동
 *    - 비동기 방식으로 안전하게 처리
 *
 * 2. Clipboard API가 실패하거나 지원되지 않으면 fallback 방식 사용:
 *    - 임시 textarea 엘리먼트를 생성
 *    - 화면에 보이지 않도록 숨김 (position: fixed, opacity: 0)
 *    - textarea에 텍스트를 넣고 선택(select)
 *    - document.execCommand('copy')로 복사
 *    - 사용 후 textarea 제거
 *
 * @param text - 클립보드에 복사할 텍스트
 * @returns Promise<boolean> - 복사 성공 여부
 *
 * @example
 * ```typescript
 * try {
 *   const success = await copyToClipboard("Hello World");
 *   if (success) {
 *     toast.success("복사되었습니다!");
 *   } else {
 *     toast.error("복사 실패");
 *   }
 * } catch (error) {
 *   console.error("복사 중 오류:", error);
 * }
 * ```
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  // 서버 사이드 렌더링 환경에서는 작동하지 않음
  if (typeof window === "undefined") {
    console.warn("copyToClipboard: window is undefined (SSR environment)");
    return false;
  }

  // 빈 문자열은 복사하지 않음
  if (!text || text.trim().length === 0) {
    console.warn("copyToClipboard: empty text");
    return false;
  }

  // 방법 1: 최신 Clipboard API 시도 (HTTPS/localhost에서만 작동)
  if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(text);
      console.log("✓ Copied using Clipboard API");
      return true;
    } catch (error) {
      // Clipboard API 실패 시 fallback으로 이동
      console.warn("Clipboard API failed, trying fallback:", error);
    }
  }

  // 방법 2: Fallback - document.execCommand 사용 (HTTP 환경에서 작동)
  try {
    // 2-1. 임시 textarea 엘리먼트 생성
    const textarea = document.createElement("textarea");

    // 2-2. 복사할 텍스트 설정
    textarea.value = text;

    // 2-3. 화면에 보이지 않도록 스타일 설정
    textarea.style.position = "fixed"; // 레이아웃에 영향 없음
    textarea.style.top = "0";
    textarea.style.left = "0";
    textarea.style.opacity = "0"; // 투명하게
    textarea.style.pointerEvents = "none"; // 클릭 이벤트 무시
    textarea.setAttribute("readonly", ""); // 읽기 전용

    // 2-4. DOM에 추가
    document.body.appendChild(textarea);

    // 2-5. iOS Safari 지원을 위한 추가 설정
    textarea.focus();
    textarea.setSelectionRange(0, text.length);

    // 2-6. 텍스트 선택
    textarea.select();

    // 2-7. 복사 명령 실행
    const successful = document.execCommand("copy");

    // 2-8. DOM에서 제거
    document.body.removeChild(textarea);

    if (successful) {
      console.log("✓ Copied using fallback method (execCommand)");
      return true;
    } else {
      console.error("✗ execCommand('copy') returned false");
      return false;
    }
  } catch (error) {
    console.error("✗ Fallback copy failed:", error);
    return false;
  }
}

/**
 * React Hook 형태의 클립보드 복사 함수
 *
 * useCopyToClipboard 훅과 호환되도록 [copied, copy] 튜플을 반환합니다.
 *
 * @returns [copiedText, copyFunction] - 복사된 텍스트와 복사 함수
 *
 * @example
 * ```typescript
 * const [copiedText, copy] = useCopyToClipboardFallback();
 *
 * const handleCopy = async () => {
 *   const success = await copy("Hello World");
 *   if (success) {
 *     toast.success("복사되었습니다!");
 *   }
 * };
 * ```
 */
export function useCopyToClipboardFallback(): [
  string | null,
  (text: string) => Promise<boolean>
] {
  const [copiedText, setCopiedText] = useState<string | null>(null);

  const copy = async (text: string): Promise<boolean> => {
    const success = await copyToClipboard(text);
    if (success) {
      setCopiedText(text);
      // 2초 후 복사 상태 초기화
      setTimeout(() => setCopiedText(null), 2000);
    }
    return success;
  };

  return [copiedText, copy];
}

// React import for hook
import { useState } from "react";
