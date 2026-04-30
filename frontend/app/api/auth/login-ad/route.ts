import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const res = await fetch(`${BACKEND_URL}/api/auth/login-ad`, {
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

    const response = NextResponse.json({ success: true });

    const cookieOpts = {
      sameSite: "lax" as const,
      path: "/",
      maxAge: 60 * 60 * 24,
      secure: false,
    };

    response.cookies.set("empno", data.empno, { ...cookieOpts, httpOnly: false });
    response.cookies.set("login_id", data.login_id, { ...cookieOpts, httpOnly: false });
    response.cookies.set("user_name", data.name, { ...cookieOpts, httpOnly: false });
    response.cookies.set("auth_token", data.token, { ...cookieOpts, httpOnly: true });

    return response;
  } catch {
    return NextResponse.json(
      { detail: "서버 연결 실패" },
      { status: 500 }
    );
  }
}
