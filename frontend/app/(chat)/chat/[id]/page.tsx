import { cookies } from "next/headers";
import { Suspense } from "react";

import { Chat } from "@/components/chat";
import { DataStreamHandler } from "@/components/data-stream-handler";
import { DEFAULT_CHAT_MODEL } from "@/lib/ai/models";

export default function Page(props: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div className="flex h-dvh" />}>
      <ChatPage params={props.params} />
    </Suspense>
  );
}

async function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const cookieStore = await cookies();

  // SSO 쿠키에서 user_id 읽기
  const userId = cookieStore.get("empno")?.value || "anonymous";

  // Fetch chat history from backend
  let initialMessages = [];
  let workspaceId = null;
  try {
    // Use relative URL for server-side fetch to Next.js API routes
    const apiUrl = `http://localhost:3000/api/messages?session_id=${id}&user_id=${userId}`;

    // Forward cookies to the API route
    const cookieHeader = cookieStore.getAll()
      .map(c => `${c.name}=${c.value}`)
      .join("; ");

    const res = await fetch(apiUrl, {
      cache: "no-store", // Always fetch latest messages
      headers: {
        Cookie: cookieHeader,
      },
    });

    if (res.ok) {
      const data = await res.json();
      initialMessages = data.messages || [];
      workspaceId = data.workspace_id || null;
    } else {
      console.error("Failed to load chat history:", res.status, res.statusText);
    }
  } catch (error) {
    console.error("Failed to load chat history:", error);
    // Fallback to empty messages on error
  }

  const chatModelFromCookie = cookieStore.get("chat-model");
  const initialChatModel = chatModelFromCookie?.value || DEFAULT_CHAT_MODEL;

  return (
    <>
      <Chat
        autoResume={false}
        id={id}
        initialChatModel={initialChatModel}
        initialMessages={initialMessages}
        isReadonly={false}
        workspaceId={workspaceId}
      />
      <DataStreamHandler />
    </>
  );
}
