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
  const sessionId = searchParams.get("session_id");
  const userId = getUserIdFromCookie(request);
  if (!userId) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const limit = searchParams.get("limit") ?? "100";

  if (!sessionId) {
    return NextResponse.json(
      { error: "session_id is required" },
      { status: 400 }
    );
  }

  const backendUrl = new URL(
    `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
    BACKEND_URL
  );
  backendUrl.searchParams.set("user_id", userId);
  backendUrl.searchParams.set("limit", limit);

  try {
    const res = await fetch(backendUrl.toString(), {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: "Failed to fetch messages" },
        { status: res.status }
      );
    }

    const data = await res.json();

    // Vercel AI SDK 형식으로 변환 (youtube_summary + 텍스트 + sources + corp_sources 순서)
    const messages =
      data.messages?.map((msg: any, index: number) => {
        const parts: any[] = [];

        // 1. 유튜브 요약 먼저 (있는 경우)
        if (msg.youtube_summary) {
          parts.push({ type: "youtube-summary", summary: msg.youtube_summary });
        }

        // 2. 텍스트 컨텐츠
        parts.push({ type: "text", text: msg.content });

        // 3. 웹 검색 출처 (있는 경우)
        if (msg.sources && msg.sources.length > 0) {
          parts.push({ type: "sources", sources: msg.sources });
        }

        // 4. Corp 문서 출처 (있는 경우)
        if (msg.corp_sources && msg.corp_sources.length > 0) {
          parts.push({ type: "corp-sources", sources: msg.corp_sources });
        }

        // 5. 차트 데이터 (있는 경우)
        if (msg.chart_data) {
          parts.push({ type: "chart-data", chartData: msg.chart_data });
        }

        return {
          id: `${sessionId}-${index}`,
          role: msg.role,
          parts,
          metadata: {
            createdAt: msg.timestamp,
          },
        };
      }) ?? [];

    return NextResponse.json({
      messages,
      total_count: data.total_count,
      workspace_id: data.workspace_id,
    });
  } catch (error) {
    console.error("Failed to fetch messages:", error);
    return NextResponse.json(
      { error: "Failed to fetch messages" },
      { status: 500 }
    );
  }
}
