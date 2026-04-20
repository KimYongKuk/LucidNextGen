import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // 백엔드 로그인 API 호출
    const res = await fetch(`${BACKEND_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { detail: data.detail || "로그인 실패" },
        { status: res.status }
      );
    }

    // 로그인 성공 → empno 쿠키 + auth_token 쿠키 설정
    const response = NextResponse.json({ success: true });

    // empno 쿠키 (기존 시스템 호환 — 클라이언트에서 읽을 수 있어야 함)
    response.cookies.set("empno", data.empno, {
      httpOnly: false,
      secure: false,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24, // 24시간
    });

    // 로그인 ID 쿠키 (UI 표시용)
    response.cookies.set("login_id", data.login_id, {
      httpOnly: false,
      secure: false,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24,
    });

    // 사용자 이름 쿠키 (UI 표시용)
    response.cookies.set("user_name", data.name, {
      httpOnly: false,
      secure: false,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24,
    });

    // JWT 토큰 쿠키 (httpOnly — XSS 방어)
    response.cookies.set("auth_token", data.token, {
      httpOnly: true,
      secure: false,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24, // 24시간
    });

    return response;
  } catch {
    return NextResponse.json(
      { detail: "서버 연결 실패" },
      { status: 500 }
    );
  }
}
