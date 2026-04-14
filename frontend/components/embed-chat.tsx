"use client";

import { useState, useCallback } from "react";
import { SquarePen } from "lucide-react";
import { useSimpleChat } from "@/hooks/use-simple-chat";
import { useDataStream } from "./data-stream-provider";
import { Messages } from "./messages";
import { MultimodalInput } from "./multimodal-input";
import { FollowUpSuggestions } from "./follow-up-suggestions";
import { DEFAULT_CHAT_MODEL } from "@/lib/ai/models";
import type { Attachment, ChatMessage } from "@/lib/types";
import { generateUUID } from "@/lib/utils";

export function EmbedChat({
  userId,
  chatMode = "outline_embed",
}: {
  userId: string;
  chatMode?: string;
}) {
  const { setDataStream } = useDataStream();
  const [sessionId, setSessionId] = useState(() => generateUUID());
  const [input, setInput] = useState("");
  const [currentModelId] = useState(DEFAULT_CHAT_MODEL);
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  const {
    messages,
    setMessages,
    sendMessage,
    status,
    stop,
    regenerate,
    followUpSuggestions,
  } = useSimpleChat({
    id: sessionId,
    messages: [],
    chatMode,
    userId,
    generateId: generateUUID,
    onData: (dataPart) => {
      setDataStream((ds) => (ds ? [...ds, dataPart] : []));
    },
    onError: (error) => {
      console.error("[EMBED_CHAT] Error:", error);
    },
  });

  const handleNewChat = useCallback(() => {
    setSessionId(generateUUID());
    setMessages([]);
    setInput("");
    setAttachments([]);
    setDataStream([]);
  }, [setMessages, setDataStream]);

  return (
    <div className="flex h-full min-w-0 flex-col bg-background">
      {/* 새 대화 버튼 — 대화가 시작된 후에만 표시 */}
      {messages.length > 0 && (
        <div className="flex justify-end px-3 py-1.5">
          <button
            onClick={handleNewChat}
            className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            title="새 대화"
          >
            <SquarePen size={14} />
            <span>새 대화</span>
          </button>
        </div>
      )}

      {/* 메시지 영역 */}
      <Messages
        chatId={sessionId}
        isArtifactVisible={false}
        isReadonly={false}
        messages={messages}
        regenerate={regenerate}
        selectedModelId={currentModelId}
        setMessages={setMessages}
        status={status}
        votes={undefined}
        workspace={undefined}
      />

      {/* 입력 영역 */}
      <div className="sticky bottom-0 z-1 mx-auto flex w-full max-w-4xl flex-col gap-2 border-t-0 bg-background px-2 pb-4 md:px-4 md:pb-4">
        {status === "ready" && !input.trim() && (
          <FollowUpSuggestions
            suggestions={followUpSuggestions}
            onSuggestionClick={(suggestion) => {
              sendMessage({
                role: "user",
                parts: [{ type: "text", text: suggestion }],
              });
            }}
          />
        )}
        <MultimodalInput
          attachments={attachments}
          chatId={sessionId}
          input={input}
          messages={messages}
          selectedModelId={currentModelId}
          sendMessage={sendMessage}
          setAttachments={setAttachments}
          setInput={setInput}
          setMessages={setMessages}
          status={status}
          stop={stop}
          embedMode
        />
      </div>
    </div>
  );
}
