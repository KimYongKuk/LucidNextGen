/**
 * API 설정 유틸리티
 */

/**
 * API URL 생성 함수
 * - 운영: nginx 프록시 경유 (same-origin, 포트 불필요)
 * - 개발: 환경변수로 직접 포트 지정
 */
export const getApiUrl = (): string => {
  // 환경변수가 설정되어 있으면 그대로 사용 (개발 환경)
  if (process.env.NEXT_PUBLIC_BACKEND_URL) {
    return process.env.NEXT_PUBLIC_BACKEND_URL;
  }

  // 운영: nginx가 /api/* 를 백엔드로 프록시하므로 same-origin
  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.host}`;
  }
  return 'http://localhost:8000';
};
