"use client";

// import { useChat } from "@ai-sdk/react";
// import { DefaultChatTransport } from "ai";
import { useRouter, useSearchParams } from "next/navigation";
import { useSimpleChat } from "@/hooks/use-simple-chat";
import { useSessionCleanup } from "@/hooks/use-session-cleanup";
import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { unstable_serialize } from "swr/infinite";
import { ChatHeader } from "@/components/chat-header";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useArtifactSelector } from "@/hooks/use-artifact";
import { useXlsxViewer, useXlsxViewerSelector } from "@/hooks/use-xlsx-viewer";
import {
  useDocumentViewer,
  useDocumentViewerSelector,
} from "@/hooks/use-document-viewer";
import { useAutoResume } from "@/hooks/use-auto-resume";
// import type { Vote } from "@/lib/db/schema";
import { ChatSDKError } from "@/lib/errors";
import type { Attachment, ChatMessage, Vote } from "@/lib/types";
import {
  fetcher,
  fetchWithErrorHandlers,
  generateUUID,
  getUserId,
} from "@/lib/utils";
import { workspaceApi, type Workspace } from "@/lib/api/workspaces";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { Artifact } from "./artifact";
import { XlsxViewerPanel } from "./xlsx-viewer-panel";
import { DocumentViewerPanel } from "./document-viewer-panel";
import { useDataStream } from "./data-stream-provider";
import { Messages } from "./messages";
import { MultimodalInput } from "./multimodal-input";
import { getChatHistoryPaginationKey } from "./sidebar-history";
import { toast } from "./toast";
import { FollowUpSuggestions } from "./follow-up-suggestions";

export function Chat({
  id,
  initialMessages,
  initialChatModel,
  isReadonly,
  autoResume,
  workspaceId,
}: {
  id: string;
  initialMessages: ChatMessage[];
  initialChatModel: string;
  isReadonly: boolean;
  autoResume: boolean;
  workspaceId?: string | null;
}) {
  const router = useRouter();
  const userId = getUserId() ?? "";

  const { mutate } = useSWRConfig();

  // Handle browser back/forward navigation
  useEffect(() => {
    const handlePopState = () => {
      // When user navigates back/forward, refresh to sync with URL
      router.refresh();
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [router]);
  const { setDataStream } = useDataStream();

  const [input, setInput] = useState<string>("");
  const [showCreditCardAlert, setShowCreditCardAlert] = useState(false);
  const [currentModelId, setCurrentModelId] = useState(initialChatModel);
  const currentModelIdRef = useRef(currentModelId);

  useEffect(() => {
    currentModelIdRef.current = currentModelId;
  }, [currentModelId]);

  const searchParams = useSearchParams();
  const query = searchParams.get("query");
  const workspaceIdParam = searchParams.get("workspace_id");
  // workspace_id is now UUID string (not numeric ID)
  const workspaceUuidFromUrl = workspaceIdParam || null;

  // workspace_id를 state로 저장하여 URL 변경에 영향받지 않도록 함
  // (첫 메시지 전송 후 URL에서 query params가 제거되어도 workspace_id 유지)
  const [stableWorkspaceId] = useState(() => workspaceId ?? workspaceUuidFromUrl);
  const effectiveWorkspaceId = stableWorkspaceId;

  const {
    messages,
    setMessages,
    sendMessage,
    status,
    stop,
    regenerate,
    resumeStream,
    followUpSuggestions,
  } = useSimpleChat({
    id,
    messages: initialMessages,
    workspaceId: effectiveWorkspaceId,
    generateId: generateUUID,
    onData: (dataPart) => {
      setDataStream((ds) => (ds ? [...ds, dataPart] : []));
    },
    onFinish: () => {
      mutate(
        unstable_serialize((pageIndex, previousPageData) => {
          const base = getChatHistoryPaginationKey(pageIndex, previousPageData);
          if (!base) return null;

          const url = new URL(base, "http://localhost");
          url.searchParams.set("user_id", userId);
          return url.pathname + url.search;
        })
      );
    },
    onError: (error) => {
      console.error("[CHAT] onError:", error);
      if (error instanceof ChatSDKError) {
        // Check if it's a credit card error
        if (
          error.message?.includes("AI Gateway requires a valid credit card")
        ) {
          setShowCreditCardAlert(true);
        } else {
          toast({
            type: "error",
            description: error.message,
          });
        }
      }
    },
  });

  const hasAppendedQueryRef = useRef(false);

  useEffect(() => {
    if (query && !hasAppendedQueryRef.current) {
      hasAppendedQueryRef.current = true;
      const path = effectiveWorkspaceId
        ? `/chat/${id}?workspace_id=${effectiveWorkspaceId}`
        : `/chat/${id}`;
      window.history.replaceState({}, "", path);

      sendMessage({
        role: "user" as const,
        parts: [{ type: "text", text: query }],
      });
    }
  }, [query, id, effectiveWorkspaceId]);

  // 세션이 속한 워크스페이스를 URL에 반영하여 사이드바 필터링 유지
  useEffect(() => {
    if (!effectiveWorkspaceId) return;
    const url = new URL(window.location.href);
    if (url.searchParams.get("workspace_id") !== effectiveWorkspaceId) {
      url.searchParams.set("workspace_id", effectiveWorkspaceId);
      window.history.replaceState({}, "", url.pathname + url.search);
    }
  }, [effectiveWorkspaceId]);

  const { data: votes } = useSWR<Vote[]>(
    messages.length >= 2 ? `/api/vote?chatId=${id}` : null,
    fetcher
  );

  const { data: workspace } = useSWR<Workspace>(
    effectiveWorkspaceId ? `/api/v1/workspaces/${effectiveWorkspaceId}?user_id=${userId}` : null,
    () => workspaceApi.get(effectiveWorkspaceId!, userId)
  );

  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const isArtifactVisible = useArtifactSelector((state) => state.isVisible);
  const isXlsxViewerOpen = useXlsxViewerSelector((state) => state.isOpen);
  const { openFile: openXlsxFile, closeViewer: closeXlsxViewer } = useXlsxViewer();
  const isDocViewerOpen = useDocumentViewerSelector((state) => state.isOpen);
  const { closeViewer: closeDocViewer } = useDocumentViewer();

  // 세션 전환 시 뷰어 닫기
  useEffect(() => {
    return () => {
      closeXlsxViewer();
      closeDocViewer();
    };
  }, [id, closeXlsxViewer, closeDocViewer]);

  // 세션에 업로드된 문서 파일 추적 (이미지는 base64로 저장되므로 제외)
  const [hasUploadedSessionFiles, setHasUploadedSessionFiles] = useState(false);

  // 세션 파일 자동 정리 훅 (세션 전환, 브라우저 닫기 시)
  useSessionCleanup(id, hasUploadedSessionFiles);

  useAutoResume({
    autoResume,
    initialMessages,
    resumeStream,
    setMessages,
  });

  // Auto-open xlsx viewer when chatbot generates an xlsx file
  const prevMsgCountRef = useRef(messages.length);
  useEffect(() => {
    // Only trigger when streaming completes and new messages arrived
    if (status !== "ready") return;
    if (messages.length <= prevMsgCountRef.current) {
      prevMsgCountRef.current = messages.length;
      return;
    }
    prevMsgCountRef.current = messages.length;

    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.role !== "assistant") return;

    const textContent =
      lastMsg.parts
        ?.filter((p: any) => p.type === "text")
        ?.map((p: any) => p.text)
        ?.join("") || "";

    const xlsxMatch =
      /\*?\*?파일명\*?\*?:\s*`?([^\n`]+\.xlsx)`?/i.exec(textContent);
    if (xlsxMatch) {
      const filename =
        xlsxMatch[1]
          .trim()
          .replace(/^[`'"*_\s]+|[`'"*_\s]+$/g, "")
          .replace(/[`'"]/g, "")
          .split(/[\\\/]/)
          .pop() || "";
      if (filename) openXlsxFile(filename);
    }
  }, [messages.length, status, openXlsxFile, messages]);

  return (
    <>
      <PanelGroup direction="horizontal" className="h-dvh">
        {/* Chat Panel */}
        <Panel defaultSize={isXlsxViewerOpen || isDocViewerOpen ? 50 : 100} minSize={30}>
          <div className="overscroll-behavior-contain flex h-full min-w-0 touch-pan-y flex-col bg-background">
            <ChatHeader
              chatId={id}
              isReadonly={isReadonly}
              workspace={workspace}
            />

            <Messages
              chatId={id}
              isArtifactVisible={isArtifactVisible}
              isReadonly={isReadonly}
              messages={messages}
              regenerate={regenerate}
              selectedModelId={initialChatModel}
              setMessages={setMessages}
              status={status}
              votes={votes}
              workspace={workspace}
            />

            <div className="sticky bottom-0 z-1 mx-auto flex w-full max-w-4xl flex-col gap-2 border-t-0 bg-background px-2 pb-3 md:px-4 md:pb-4">
              {!isReadonly && status === 'ready' && !input.trim() && (
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
              {!isReadonly && (
                <MultimodalInput
                  attachments={attachments}
                  chatId={id}
                  input={input}
                  messages={messages}
                  onFileUploaded={() => setHasUploadedSessionFiles(true)}
                  onModelChange={setCurrentModelId}
                  selectedModelId={currentModelId}
                  sendMessage={sendMessage}
                  setAttachments={setAttachments}
                  setInput={setInput}
                  setMessages={setMessages}
                  status={status}
                  stop={stop}
                  workspaceId={effectiveWorkspaceId}
                />
              )}
            </div>
          </div>
        </Panel>

        {/* XLSX Viewer Panel */}
        {isXlsxViewerOpen && (
          <>
            <PanelResizeHandle className="w-1.5 bg-border hover:bg-primary/20 transition-colors" />
            <Panel defaultSize={50} minSize={25}>
              <XlsxViewerPanel />
            </Panel>
          </>
        )}

        {/* Document Viewer Panel (PDF / DOCX) */}
        {isDocViewerOpen && !isXlsxViewerOpen && (
          <>
            <PanelResizeHandle className="w-1.5 bg-border hover:bg-primary/20 transition-colors" />
            <Panel defaultSize={50} minSize={25}>
              <DocumentViewerPanel />
            </Panel>
          </>
        )}
      </PanelGroup>

      <Artifact
        attachments={attachments}
        chatId={id}
        input={input}
        isReadonly={isReadonly}
        messages={messages}
        regenerate={regenerate}
        selectedModelId={currentModelId}
        sendMessage={sendMessage}
        setAttachments={setAttachments}
        setInput={setInput}
        setMessages={setMessages}
        status={status}
        stop={stop}
        votes={votes}
      />

      <AlertDialog
        onOpenChange={setShowCreditCardAlert}
        open={showCreditCardAlert}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Activate AI Gateway</AlertDialogTitle>
            <AlertDialogDescription>
              This application requires{" "}
              {process.env.NODE_ENV === "production" ? "the owner" : "you"} to
              activate Vercel AI Gateway.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                window.open(
                  "https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai%3Fmodal%3Dadd-credit-card",
                  "_blank"
                );
                window.location.href = "/";
              }}
            >
              Activate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
