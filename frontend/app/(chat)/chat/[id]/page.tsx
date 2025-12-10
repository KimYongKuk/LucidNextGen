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

  // Since we removed the DB, we cannot retrieve chat history.
  // We will render the chat component with empty messages.
  // In a real integration, you would fetch history from your backend here.

  const cookieStore = await cookies();
  const chatModelFromCookie = cookieStore.get("chat-model");
  const initialChatModel = chatModelFromCookie?.value || DEFAULT_CHAT_MODEL;

  return (
    <>
      <Chat
        autoResume={false}
        id={id}
        initialChatModel={initialChatModel}
        initialMessages={[]} // History is not persisted in this UI-only version
        initialVisibilityType="private"
        isReadonly={false}
      />
      <DataStreamHandler />
    </>
  );
}
