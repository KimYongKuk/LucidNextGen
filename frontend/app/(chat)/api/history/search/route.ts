import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

// SSO 쿠키에서 user_id 추출 (인증 필수)
const getUserIdFromCookie = (request: Request): string | null => {
  const cookieHeader = request.headers.get("cookie") || "";
  const empnoCookie = cookieHeader
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith("empno="));
  return empnoCookie?.split("=")[1] || null;
};

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const userId = getUserIdFromCookie(request);
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const query = searchParams.get("q") ?? "";
  const limit = searchParams.get("limit") ?? "20";

  if (!query) {
    return NextResponse.json({ chats: [], query: "" });
  }

  const backendUrl = new URL("/api/v1/chat/sessions/search", BACKEND_URL);
  backendUrl.searchParams.set("user_id", userId);
  backendUrl.searchParams.set("q", query);
  backendUrl.searchParams.set("limit", limit);

  try {
    const cookieHeader = request.headers.get("cookie") || "";
    const res = await fetch(backendUrl.toString(), {
      method: "GET",
      headers: { "Content-Type": "application/json", Cookie: cookieHeader },
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: "Search failed" },
        { status: res.status }
      );
    }

    const data = await res.json();

    // Normalize backend fields to frontend shape
    const chats =
      data.sessions?.map((session: any) => ({
        id: session.session_id,
        title: session.title || "(제목 없음)",
        createdAt: session.created_at,
        updatedAt: session.updated_at,
        chatMode: session.chat_mode,
        isPinned: session.is_pinned,
        workspace_id: session.workspace_id,
      })) ?? [];

    return NextResponse.json({
      chats,
      query: data.query,
    });
  } catch {
    return NextResponse.json({ error: "Search failed" }, { status: 500 });
  }
}
