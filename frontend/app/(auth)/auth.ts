/**
 * Mock auth module
 * 실제 인증 시스템을 사용하지 않으므로 항상 인증된 것으로 처리
 */

export type UserType = "guest" | "regular" | "admin";

export async function auth() {
  // 항상 인증된 세션 반환 (mock)
  return {
    user: {
      id: "anonymous",
      email: "anonymous@localhost",
      name: "Anonymous User",
    },
  };
}

export function signOut(options?: { redirectTo?: string }) {
  // No-op: 로그아웃 기능 없음
  return Promise.resolve();
}

export function signIn() {
  // No-op: 로그인 기능 없음
  return Promise.resolve();
}
