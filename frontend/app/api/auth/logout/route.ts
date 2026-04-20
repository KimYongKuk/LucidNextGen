import { NextResponse } from "next/server";

export async function POST() {
  const response = NextResponse.json({ success: true });

  // empno 쿠키 삭제 (클라이언트용)
  response.cookies.set("empno", "", {
    path: "/",
    maxAge: 0,
  });

  // login_id 쿠키 삭제
  response.cookies.set("login_id", "", {
    path: "/",
    maxAge: 0,
  });

  // user_name 쿠키 삭제
  response.cookies.set("user_name", "", {
    path: "/",
    maxAge: 0,
  });

  // auth_token 쿠키 삭제 (JWT)
  response.cookies.set("auth_token", "", {
    path: "/",
    maxAge: 0,
    httpOnly: true,
  });

  return response;
}
