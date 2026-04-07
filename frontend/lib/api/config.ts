/**
 * API 설정 유틸리티
 */

/**
 * API URL 생성 함수
 * - 운영: nginx 프록시 경유 (same-origin, 포트 불필요)
 * - 개발: 환경변수로 직접 포트 지정
 */
export const getApiUrl = (): string => {
  if (typeof window !== 'undefined') {
    // 개발 모드: 백엔드 직접 호출 (Next.js rewrites SSE 버퍼링 우회)
    const devBackend = process.env.NEXT_PUBLIC_BACKEND_URL;
    if (devBackend) {
      return devBackend;
    }
    // 운영: nginx same-origin 경유
    return `${window.location.protocol}//${window.location.host}`;
  }
  // SSR: 환경변수 → 폴백
  return process.env.BACKEND_URL || 'http://localhost:8000';
};
