/**
 * API 설정 유틸리티
 */

/**
 * API URL 생성 함수
 * 프론트엔드와 백엔드가 같은 서버에서 실행되므로 현재 호스트 사용
 */
export const getApiUrl = (): string => {
  if (typeof window !== 'undefined') {
    // 브라우저의 현재 호스트명을 사용 (localhost든 IP든 동일하게 처리)
    const currentHost = window.location.hostname;
    return `http://${currentHost}:8000`;
  }
  return 'http://localhost:8000';
};
