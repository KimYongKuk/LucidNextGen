import { NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  const range = searchParams.get("range") ?? "recent7";
  const chatMode = searchParams.get("chat_mode") ?? undefined;
  const limit = searchParams.get("limit") ?? "20";
  const cursor = searchParams.get("cursor") ?? undefined;
  const workspaceId = searchParams.get("workspace_id") ?? undefined;

  const backendUrl = new URL("/api/v1/chat/sessions", BACKEND_URL);
  backendUrl.searchParams.set("user_id", userId);
  backendUrl.searchParams.set("range", range);
  backendUrl.searchParams.set("limit", limit);
  if (chatMode) backendUrl.searchParams.set("chat_mode", chatMode);
  if (cursor) backendUrl.searchParams.set("cursor", cursor);
  if (workspaceId) backendUrl.searchParams.set("workspace_id", workspaceId);

  try {
    const res = await fetch(backendUrl.toString(), {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: "Failed to fetch history" },
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
      })) ?? [];

    return NextResponse.json({
      chats,
      hasMore: data.hasMore ?? false,
      nextCursor: data.nextCursor ?? null,
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to fetch history" },
      { status: 500 }
    );
  }
}

export async function DELETE(request: Request) {
  const { searchParams } = new URL(request.url);
  const sessionId = searchParams.get("id");
  const userId = getUserIdFromCookie(request);
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  if (!sessionId) {
    return NextResponse.json({ error: "id is required" }, { status: 400 });
  }

  const backendUrl = new URL(
    `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}`,
    BACKEND_URL
  );
  backendUrl.searchParams.set("user_id", userId);

  try {
    const res = await fetch(backendUrl.toString(), {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: "Failed to delete session" },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: "Failed to delete session" },
      { status: 500 }
    );
  }
}
