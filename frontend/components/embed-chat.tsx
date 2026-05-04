"use client";

import { useState, useCallback, useEffect, useRef, type ReactNode } from "react";
import { SquarePen, ExternalLink, Monitor, X } from "lucide-react";
import { useSimpleChat } from "@/hooks/use-simple-chat";
import { useDataStream } from "./data-stream-provider";
import { Messages } from "./messages";
import { MultimodalInput } from "./multimodal-input";
import { FollowUpSuggestions } from "./follow-up-suggestions";
import { DEFAULT_CHAT_MODEL } from "@/lib/ai/models";
import { getApiUrl } from "@/lib/api/config";
import type { Attachment, ChatMessage } from "@/lib/types";
import { generateUUID } from "@/lib/utils";

// 그룹웨어 위젯 화면 공유 — 부모 페이지에서 받는 메타정보
type ParentPageInfo = { url: string; title: string };

// 부모 DOM 본문 추출 응답 대기 타임아웃
const PAGE_CONTENT_REQUEST_TIMEOUT_MS = 3000;

// 화면 공유 기능 on/off — Next.js NEXT_PUBLIC_* 는 빌드 타임 임베드.
// 기본 false. 활성화하려면 backend/.env에 NEXT_PUBLIC_PAGE_SHARE_ENABLED=true
// 추가하고 deploy.bat의 .env.local 생성 블록(Step 2.5)에서 propagate 필요.
const PAGE_SHARE_ENABLED = process.env.NEXT_PUBLIC_PAGE_SHARE_ENABLED === 'true';

export function EmbedChat({
  userId,
  widgetAuthToken,
  gossoCookie,
  chatMode = "outline_embed",
  initialSessionId,
  onNewChat,
  renderEmptyExamples,
}: {
  userId: string;
  widgetAuthToken?: string;
  gossoCookie?: string;
  chatMode?: string;
  initialSessionId?: string;
  onNewChat?: () => void;
  renderEmptyExamples?: (args: {
    chatId: string;
    onSelect: (text: string) => void;
  }) => ReactNode;
}) {
  const { setDataStream } = useDataStream();
  const [sessionId, setSessionId] = useState(() => initialSessionId || generateUUID());
  const [input, setInput] = useState("");
  const [currentModelId] = useState(DEFAULT_CHAT_MODEL);
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  // ─── 그룹웨어 위젯: 현재 화면 공유 상태 ───
  const isGroupwareEmbed = chatMode === "groupware_embed";
  // PAGE_SHARE_ENABLED 환경변수가 false면 화면 공유 관련 모든 동작 비활성
  // (chip 미표시 + DOM 추출 미수행 + page_context 미전송)
  const enablePageShare = isGroupwareEmbed && PAGE_SHARE_ENABLED;
  const [parentPage, setParentPage] = useState<ParentPageInfo | null>(null);
  const [pageShareEnabled, setPageShareEnabled] = useState(true);
  const pageShareEnabledRef = useRef(true);
  pageShareEnabledRef.current = pageShareEnabled;
  const parentPageRef = useRef<ParentPageInfo | null>(null);
  parentPageRef.current = parentPage;

  // 부모 위젯에서 오는 postMessage 리스너
  useEffect(() => {
    if (!enablePageShare) return;
    const handler = (e: MessageEvent) => {
      if (!e.data || typeof e.data !== "object") return;
      if (e.data.type === "lucid-page-context") {
        const next = { url: String(e.data.url || ""), title: String(e.data.title || "") };
        // 부모 페이지가 바뀌면 (URL 변화) 자동으로 공유 재활성화 (Gemini 동작과 동일)
        const prev = parentPageRef.current;
        if (!prev || prev.url !== next.url) {
          setPageShareEnabled(true);
        }
        setParentPage(next);
      }
    };
    window.addEventListener("message", handler);
    // 마운트 직후 한 번 부모에 컨텍스트 송신 요청 (race 방지)
    if (window.parent !== window) {
      window.parent.postMessage({ type: "lucid-request-page-context" }, "*");
    }
    return () => window.removeEventListener("message", handler);
  }, [enablePageShare]);

  // sendMessage 직전 부모 DOM 본문 추출 — useSimpleChat이 호출
  const getPageContext = useCallback(async () => {
    if (!enablePageShare) return null;
    if (!pageShareEnabledRef.current) return null;
    if (!parentPageRef.current) return null;
    if (window.parent === window) return null;

    return await new Promise<{ url?: string; title?: string; content?: string } | null>((resolve) => {
      const requestId = generateUUID();
      let settled = false;
      const onResp = (e: MessageEvent) => {
        if (!e.data || e.data.type !== "lucid-page-content" || e.data.requestId !== requestId) return;
        if (settled) return;
        settled = true;
        window.removeEventListener("message", onResp);
        if (e.data.success) {
          resolve({
            url: String(e.data.url || ""),
            title: String(e.data.title || ""),
            content: String(e.data.content || ""),
          });
        } else {
          resolve(null);
        }
      };
      window.addEventListener("message", onResp);
      window.parent.postMessage({ type: "lucid-request-page-content", requestId }, "*");
      setTimeout(() => {
        if (settled) return;
        settled = true;
        window.removeEventListener("message", onResp);
        console.warn("[EMBED_CHAT] page content request timed out");
        // 타임아웃 시 메타정보만이라도 첨부 (제목/URL은 부모 mount 직후 받았음)
        const p = parentPageRef.current;
        resolve(p ? { url: p.url, title: p.title, content: "" } : null);
      }, PAGE_CONTENT_REQUEST_TIMEOUT_MS);
    });
  }, [enablePageShare]);

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
    widgetAuthToken,
    gossoCookie,
    getPageContext,
    generateId: generateUUID,
    onData: (dataPart) => {
      setDataStream((ds) => (ds ? [...ds, dataPart] : []));
    },
    onError: (error) => {
      console.error("[EMBED_CHAT] Error:", error);
    },
  });

  // initialSessionId가 있으면 기존 대화 메시지 복원
  useEffect(() => {
    if (!initialSessionId || userId === "anonymous") return;

    const loadMessages = async () => {
      try {
        const baseUrl = getApiUrl();
        const res = await fetch(
          `${baseUrl}/api/v1/chat/sessions/${initialSessionId}/messages?user_id=${encodeURIComponent(userId)}`,
          {
            credentials: 'include',
            headers: widgetAuthToken ? { 'X-Widget-Auth': widgetAuthToken } : {},
          }
        );
        if (!res.ok) return;
        const data = await res.json();
        if (!data.messages || data.messages.length === 0) return;

        // 백엔드 형식 → ChatMessage 형식 변환
        const restored: ChatMessage[] = data.messages.map((msg: { role: string; content: string; sources?: unknown[]; corp_sources?: unknown[] }) => ({
          id: generateUUID(),
          role: msg.role as "user" | "assistant",
          parts: [{ type: "text" as const, text: msg.content }],
          ...(msg.sources && msg.sources.length > 0 ? { sources: msg.sources } : {}),
          ...(msg.corp_sources && msg.corp_sources.length > 0 ? { corpSources: msg.corp_sources } : {}),
        }));

        setMessages(restored);
      } catch (e) {
        console.error("[EMBED_CHAT] Failed to restore messages:", e);
      }
    };

    loadMessages();
  }, [initialSessionId, userId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNewChat = useCallback(() => {
    setSessionId(generateUUID());
    setMessages([]);
    setInput("");
    setAttachments([]);
    setDataStream([]);
    onNewChat?.();
  }, [setMessages, setDataStream, onNewChat]);

  const handleOpenInMainApp = useCallback(async () => {
    if (typeof window === "undefined") return;

    const baseUrl = `${window.location.origin}/chat/${sessionId}`;
    let targetUrl = baseUrl;

    // 위젯 인증 토큰이 있으면 본체 SSO empno로 변환해서 ?empno=&gosso= 부착
    // → 본체 미들웨어가 SSO 흐름 그대로 처리 → auth_token 쿠키 발급 → 채팅 화면 진입
    if (widgetAuthToken) {
      try {
        const res = await fetch(`${getApiUrl()}/api/auth/widget-to-sso`, {
          method: "POST",
          headers: { "X-Widget-Auth": widgetAuthToken },
        });
        if (res.ok) {
          const { encrypted_empno } = await res.json();
          const params = new URLSearchParams({ empno: encrypted_empno });
          if (gossoCookie) params.set("gosso", gossoCookie);
          targetUrl = `${baseUrl}?${params.toString()}`;
        }
      } catch {
        // 변환 실패 시 fallback — 사용자는 로그인 화면을 보게 됨 (기존 동작)
      }
    }

    window.open(targetUrl, "_blank", "noopener,noreferrer");
  }, [sessionId, widgetAuthToken, gossoCookie]);

  return (
    <div className="flex h-full min-w-0 flex-col overflow-x-hidden bg-background">
      {/* 새 대화 / 본체에서 열기 — 대화가 시작된 후에만 표시 */}
      {messages.length > 0 && (
        <div className="flex justify-end gap-1 px-3 py-1.5">
          {chatMode === "groupware_embed" && (
            <button
              onClick={handleOpenInMainApp}
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="본체에서 열기 (현재 대화 이어서)"
            >
              <ExternalLink size={14} />
              <span>본체에서 열기</span>
            </button>
          )}
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
        {status === "ready" && !input.trim() && messages.length === 0 && renderEmptyExamples?.({
          chatId: sessionId,
          onSelect: (text) => {
            sendMessage({
              role: "user",
              parts: [{ type: "text", text }],
            });
          },
        })}
        {status === "ready" && !input.trim() && messages.length > 0 && (
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
        {/* 그룹웨어 위젯: 현재 화면 공유 chip (input 바로 위) */}
        {enablePageShare && parentPage && pageShareEnabled && (
          <div className="flex items-center justify-start">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/60 px-2.5 py-1 text-xs text-muted-foreground max-w-full">
              <Monitor size={12} className="shrink-0" />
              <span className="truncate max-w-[220px]" title={parentPage.title || parentPage.url}>
                {parentPage.title || parentPage.url || "현재 화면"} 공유 중
              </span>
              <button
                type="button"
                onClick={() => setPageShareEnabled(false)}
                className="ml-0.5 rounded-full p-0.5 hover:bg-foreground/10 transition-colors"
                title="화면 공유 끄기"
                aria-label="화면 공유 끄기"
              >
                <X size={12} />
              </button>
            </div>
          </div>
        )}
        {enablePageShare && parentPage && !pageShareEnabled && (
          <div className="flex items-center justify-start">
            <button
              type="button"
              onClick={() => setPageShareEnabled(true)}
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              title="현재 화면 다시 공유하기"
            >
              <Monitor size={12} />
              <span>지금 보는 화면 공유</span>
            </button>
          </div>
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
