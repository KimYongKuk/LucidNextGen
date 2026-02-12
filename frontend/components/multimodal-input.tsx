"use client";

import type { UseChatHelpers } from "@ai-sdk/react";
import { Trigger } from "@radix-ui/react-select";
import type { UIMessage } from "ai";
import equal from "fast-deep-equal";
import {
  type ChangeEvent,
  type Dispatch,
  memo,
  type SetStateAction,
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";
import { useLocalStorage, useWindowSize } from "usehooks-ts";
import { saveChatModelAsCookie } from "@/app/(chat)/actions";
import { SelectItem } from "@/components/ui/select";
import { chatModels } from "@/lib/ai/models";
import type { Attachment, ChatMessage } from "@/lib/types";
import { cn, getUserId } from "@/lib/utils";
import { getApiUrl } from "@/lib/api/config";
import {
  PromptInput,
  PromptInputModelSelect,
  PromptInputModelSelectContent,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputToolbar,
  PromptInputTools,
} from "./elements/prompt-input";
import {
  ArrowUpIcon,
  ChevronDownIcon,
  CpuIcon,
  MicrophoneIcon,
  PaperclipIcon,
  StopIcon,
} from "./icons";
import { PreviewAttachment } from "./preview-attachment";
import { SuggestedActions } from "./suggested-actions";
import { Button } from "./ui/button";

function PureMultimodalInput({
  chatId,
  input,
  setInput,
  status,
  stop,
  attachments,
  setAttachments,
  messages,
  setMessages,
  sendMessage,
  className,
  selectedModelId,
  onModelChange,
  onFileUploaded,
  workspaceId,
}: {
  chatId: string;
  input: string;
  setInput: Dispatch<SetStateAction<string>>;
  status: UseChatHelpers<ChatMessage>["status"];
  stop: () => void;
  attachments: Attachment[];
  setAttachments: Dispatch<SetStateAction<Attachment[]>>;
  messages: UIMessage[];
  setMessages: UseChatHelpers<ChatMessage>["setMessages"];
  sendMessage: (message: any) => Promise<void>;
  className?: string;
  selectedModelId: string;
  onModelChange?: (modelId: string) => void;
  onFileUploaded?: () => void;
  workspaceId?: string | null;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { width } = useWindowSize();

  // 폴링 cleanup을 위한 refs
  const pollIntervalsRef = useRef<Set<NodeJS.Timeout>>(new Set());
  const pollAbortControllerRef = useRef<AbortController | null>(null);

  const adjustHeight = useCallback(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "44px";
    }
  }, []);

  useEffect(() => {
    if (textareaRef.current) {
      adjustHeight();
    }
  }, [adjustHeight]);

  const resetHeight = useCallback(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "44px";
    }
  }, []);

  const [localStorageInput, setLocalStorageInput] = useLocalStorage(
    "input",
    ""
  );

  useEffect(() => {
    if (textareaRef.current) {
      const domValue = textareaRef.current.value;
      // Prefer DOM value over localStorage to handle hydration
      const finalValue = domValue || localStorageInput || "";
      setInput(finalValue);
      adjustHeight();
    }
    // Only run once after hydration
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adjustHeight, localStorageInput, setInput]);

  useEffect(() => {
    setLocalStorageInput(input);
  }, [input, setLocalStorageInput]);

  // 응답 완료 후 입력 필드에 포커스
  const prevStatusRef = useRef(status);
  useEffect(() => {
    // streaming/submitted → ready 로 바뀌면 포커스
    if (prevStatusRef.current !== 'ready' && status === 'ready') {
      if (width && width > 768) {
        textareaRef.current?.focus();
      }
    }
    prevStatusRef.current = status;
  }, [status, width]);

  const handleInput = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
  };

  const fileInputRef = useRef<HTMLInputElement>(null);

  const submitForm = useCallback(() => {
    window.history.pushState({}, "", `/chat/${chatId}`);

    sendMessage({
      role: "user",
      parts: [
        ...attachments.map((attachment) => ({
          type: "file" as const,
          url: attachment.url,
          name: attachment.name,
          mediaType: attachment.contentType,
        })),
        {
          type: "text",
          text: input,
        },
      ],
    });

    setAttachments([]);
    setLocalStorageInput("");
    resetHeight();
    setInput("");

    if (width && width > 768) {
      textareaRef.current?.focus();
    }
  }, [
    input,
    setInput,
    attachments,
    sendMessage,
    setAttachments,
    setLocalStorageInput,
    width,
    chatId,
    resetHeight,
  ]);

  // 최대 파일 크기 (10MB)
  const MAX_FILE_SIZE = 10 * 1024 * 1024;

  const uploadFile = useCallback(async (file: File) => {
    // 파일 크기 검증 (10MB)
    if (file.size > MAX_FILE_SIZE) {
      toast.error(`파일 크기가 10MB를 초과합니다: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)}MB)`);
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("user_id", getUserId() ?? "");
    formData.append("session_id", chatId);

    // Create placeholder attachment with uploading status
    const placeholderId = `uploading-${Date.now()}-${file.name}`;
    const uploadingAttachment: Attachment = {
      url: placeholderId,
      name: file.name,
      contentType: file.type,
      status: 'uploading',
    };

    // Add to attachments immediately to show loading state
    setAttachments(prev => [...prev, uploadingAttachment]);

    try {
      const isImage = file.type.startsWith('image/');
      const apiUrl = isImage
        ? '/api/v1/upload/image'
        : '/api/v1/upload/file';

      const response = await fetch(apiUrl, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: Upload failed`);
      }

      const data = await response.json();

      if (isImage) {
        // Image: immediate base64 response
        const { media_type, base64_data, filename } = data;
        if (!base64_data) {
          throw new Error("Image upload failed: empty base64 data");
        }

        // Update attachment with actual data
        setAttachments(prev =>
          prev.map(att =>
            att.url === placeholderId
              ? {
                url: `data:${media_type};base64,${base64_data}`,
                name: filename,
                contentType: media_type,
                status: 'ready',
              }
              : att
          )
        );

        toast.success(`이미지 업로드 완료: ${filename}`);

      } else {
        // Document: handle background processing
        if (data.status === "processing") {
          // Update status to processing
          setAttachments(prev =>
            prev.map(att =>
              att.url === placeholderId
                ? {
                  ...att,
                  status: 'processing',
                  url: data.file_id, // Use file_id as temporary URL for polling
                  name: data.filename,
                }
                : att
            )
          );

          // Poll for status with cleanup support
          const fileId = data.file_id;
          const controller = new AbortController();
          pollAbortControllerRef.current = controller;
          let retryCount = 0;
          const maxRetries = 150; // 5분 (2초 × 150)

          const pollInterval = setInterval(async () => {
            // 중단 신호 확인
            if (controller.signal.aborted) {
              clearInterval(pollInterval);
              pollIntervalsRef.current.delete(pollInterval);
              return;
            }

            // 최대 재시도 초과
            if (retryCount >= maxRetries) {
              clearInterval(pollInterval);
              pollIntervalsRef.current.delete(pollInterval);
              setAttachments(prev =>
                prev.map(att =>
                  att.url === fileId
                    ? { ...att, status: 'error', error: 'Processing timeout' }
                    : att
                )
              );
              toast.error(`파일 처리 시간 초과: ${data.filename}`);
              return;
            }

            try {
              const statusRes = await fetch(`/api/v1/upload/status/${fileId}`, {
                signal: controller.signal
              });
              if (!statusRes.ok) {
                retryCount++;
                return; // Skip this poll if error
              }

              const statusData = await statusRes.json();

              if (statusData.status === "completed") {
                clearInterval(pollInterval);
                pollIntervalsRef.current.delete(pollInterval);
                setAttachments(prev =>
                  prev.map(att =>
                    att.url === fileId
                      ? {
                        ...att,
                        status: 'ready',
                        url: statusData.filename, // Final URL is filename for RAG
                        name: statusData.filename,
                      }
                      : att
                  )
                );
                // 문서 파일 업로드 완료 알림 (세션 정리용)
                onFileUploaded?.();
                toast.success(`파일 처리 완료: ${statusData.filename}`);
              } else if (statusData.status === "failed") {
                clearInterval(pollInterval);
                pollIntervalsRef.current.delete(pollInterval);
                throw new Error(statusData.message || "Processing failed");
              }
              // If processing, continue polling
              retryCount++;
            } catch (err) {
              // AbortError는 정상적인 취소이므로 무시
              if (err instanceof Error && err.name === 'AbortError') {
                clearInterval(pollInterval);
                pollIntervalsRef.current.delete(pollInterval);
                return;
              }
              clearInterval(pollInterval);
              pollIntervalsRef.current.delete(pollInterval);
              console.error("Polling error:", err);
              setAttachments(prev =>
                prev.map(att =>
                  att.url === fileId
                    ? {
                      ...att,
                      status: 'error',
                      error: err instanceof Error ? err.message : 'Processing failed'
                    }
                    : att
                )
              );
              toast.error(`파일 처리 실패: ${data.filename}`);
            }
          }, 2000); // Check every 2 seconds

          // 인터벌 추적
          pollIntervalsRef.current.add(pollInterval);

        } else if (data.status === "success") {
          // Immediate success (fallback for small files if sync)
          setAttachments(prev =>
            prev.map(att =>
              att.url === placeholderId
                ? {
                  url: data.filename,
                  name: data.filename,
                  contentType: file.type,
                  status: 'ready',
                }
                : att
            )
          );
          // 문서 파일 업로드 완료 알림 (세션 정리용)
          onFileUploaded?.();
          toast.success(`파일 업로드 완료: ${data.filename}`);
        } else {
          throw new Error(data.message || "Upload failed");
        }
      }

    } catch (error) {
      console.error("Upload error:", error);

      // Mark attachment as error
      setAttachments(prev =>
        prev.map(att =>
          att.url === placeholderId
            ? {
              ...att,
              status: 'error',
              error: error instanceof Error ? error.message : 'Upload failed'
            }
            : att
        )
      );

      toast.error(
        error instanceof Error
          ? error.message
          : "파일 업로드 실패. 다시 시도해주세요."
      );
    }
  }, [chatId, setAttachments, onFileUploaded]);

  const deleteSessionFiles = useCallback(async () => {
    try {
      const baseUrl = getApiUrl();
      const response = await fetch(
        `${baseUrl}/api/v1/upload/session/${chatId}`,
        {
          method: "DELETE",
        }
      );

      if (response.ok) {
        console.log(`Session ${chatId} files deleted`);
      }
    } catch (error) {
      console.error("Failed to delete session files:", error);
    }
  }, [chatId]);



  const handleFileChange = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files || []);

      // Process files sequentially (better UX for multiple files)
      for (const file of files) {
        await uploadFile(file);
      }

      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    },
    [uploadFile]
  );

  const handlePaste = useCallback(
    async (event: ClipboardEvent) => {
      const items = event.clipboardData?.items;
      if (!items) {
        return;
      }

      const imageItems = Array.from(items).filter((item) =>
        item.type.startsWith("image/")
      );

      if (imageItems.length === 0) {
        return;
      }

      // Prevent default paste behavior for images
      event.preventDefault();

      try {
        const imageFiles = imageItems
          .map((item) => item.getAsFile())
          .filter((file): file is File => file !== null);

        // Upload images sequentially
        for (const file of imageFiles) {
          await uploadFile(file);
        }
      } catch (error) {
        console.error("Error uploading pasted images:", error);
        toast.error("Failed to upload pasted image(s)");
      }
    },
    [uploadFile]
  );

  // Add paste event listener to textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.addEventListener("paste", handlePaste);
    return () => textarea.removeEventListener("paste", handlePaste);
  }, [handlePaste]);

  // 컴포넌트 언마운트 시 모든 폴링 정리
  useEffect(() => {
    return () => {
      // 모든 폴링 인터벌 정리
      pollIntervalsRef.current.forEach(interval => clearInterval(interval));
      pollIntervalsRef.current.clear();
      // AbortController로 진행 중인 fetch 취소
      pollAbortControllerRef.current?.abort();
    };
  }, []);

  return (
    <div className={cn("relative flex w-full flex-col gap-4", className)}>
      {messages.length === 0 &&
        attachments.length === 0 &&
        !workspaceId && (
          <SuggestedActions
            chatId={chatId}
            sendMessage={sendMessage}
          />
        )}

      <input
        className="-top-4 -left-4 pointer-events-none fixed size-0.5 opacity-0"
        multiple
        accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.html,.htm,.csv,image/*"
        onChange={handleFileChange}
        ref={fileInputRef}
        tabIndex={-1}
        type="file"
      />

      <PromptInput
        className="rounded-xl border border-border bg-background p-3 shadow-xs transition-all duration-200 focus-within:border-border hover:border-muted-foreground/50"
        onSubmit={(event) => {
          event.preventDefault();
          // 텍스트가 없으면 제출 안함
          if (!input.trim()) {
            return;
          }
          // 파일 업로드 중이면 제출 안함
          if (attachments.some(att => att.status === 'uploading' || att.status === 'processing')) {
            toast.error("파일 업로드가 완료될 때까지 기다려주세요.");
            return;
          }
          if (status !== "ready") {
            toast.error("Please wait for the model to finish its response!");
          } else {
            submitForm();
          }
        }}
      >
        {attachments.length > 0 && (
          <div
            className="flex flex-row items-end gap-2 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
            data-testid="attachments-preview"
          >
            {attachments.map((attachment) => (
              <PreviewAttachment
                attachment={attachment}
                key={attachment.url}
                isUploading={attachment.status === 'uploading' || attachment.status === 'processing'}
                onRemove={async () => {
                  setAttachments((currentAttachments) =>
                    currentAttachments.filter((a) => a.url !== attachment.url)
                  );
                  if (fileInputRef.current) {
                    fileInputRef.current.value = "";
                  }

                  // 파일 타입 확인 (이미지가 아닌 문서 파일만 백엔드에서 삭제)
                  const isDocument = !attachment.url.startsWith('data:');
                  if (isDocument && attachment.status === 'ready') {
                    // 백엔드 세션 파일 삭제
                    await deleteSessionFiles();
                  }
                }}
              />
            ))}
          </div>
        )}
        <div className="flex flex-row items-start gap-1 sm:gap-2">
          <PromptInputTextarea
            autoFocus
            className="grow resize-none border-0! border-none! bg-transparent p-2 text-sm text-left! outline-none ring-0 [-ms-overflow-style:none] [scrollbar-width:none] placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 [&::-webkit-scrollbar]:hidden"
            data-testid="multimodal-input"
            disabled={false}
            disableAutoResize={true}
            maxHeight={200}
            minHeight={44}
            onChange={handleInput}
            placeholder={
              status === "streaming"
                ? "Lucid can make mistakes. Please double-check the response."
                : "Lucid can make mistakes. Please double-check the response."
            }
            readOnly={false}
            ref={textareaRef}
            rows={1}
            style={{ textAlign: 'left', direction: 'ltr' }}
            value={input}
          />
        </div>
        <PromptInputToolbar className="!border-top-0 border-t-0! p-0 shadow-none dark:border-0 dark:border-transparent!">
          <PromptInputTools className="gap-0 sm:gap-0.5">
            <AttachmentsButton
              fileInputRef={fileInputRef}
              selectedModelId={selectedModelId}
              status={status}
            />
            <VoiceRecordButton
              status={status}
              onTranscript={(text) => setInput((prev) => prev + text)}
            />
            {/* 모델 선택 UI 숨김 - 백엔드에서 모델 고정 사용 */}
            {/* <ModelSelectorCompact
              onModelChange={onModelChange}
              selectedModelId={selectedModelId}
            /> */}
          </PromptInputTools>

          {status === "streaming" || status === "submitted" ? (
            <StopButton setMessages={setMessages} stop={stop} />
          ) : (
            <PromptInputSubmit
              className="size-8 rounded-full bg-primary text-primary-foreground transition-colors duration-200 hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground"
              data-testid="send-button"
              disabled={
                !input.trim() ||
                attachments.some(att => att.status === 'uploading' || att.status === 'processing')
              }
              status={status}
            >
              <ArrowUpIcon size={14} />
            </PromptInputSubmit>
          )}
        </PromptInputToolbar>
      </PromptInput>
    </div>
  );
}

export const MultimodalInput = memo(
  PureMultimodalInput,
  (prevProps, nextProps) => {
    if (prevProps.input !== nextProps.input) {
      return false;
    }
    if (prevProps.status !== nextProps.status) {
      return false;
    }
    if (!equal(prevProps.attachments, nextProps.attachments)) {
      return false;
    }
    if (prevProps.selectedModelId !== nextProps.selectedModelId) {
      return false;
    }

    return true;
  }
);

function PureAttachmentsButton({
  fileInputRef,
  status,
  selectedModelId,
}: {
  fileInputRef: React.MutableRefObject<HTMLInputElement | null>;
  status: UseChatHelpers<ChatMessage>["status"];
  selectedModelId: string;
}) {
  const isReasoningModel = selectedModelId === "chat-model-reasoning";

  return (
    <Button
      className="aspect-square h-8 rounded-lg p-1 transition-colors hover:bg-accent"
      data-testid="attachments-button"
      disabled={status !== "ready" || isReasoningModel}
      onClick={(event) => {
        event.preventDefault();
        fileInputRef.current?.click();
      }}
      variant="ghost"
    >
      <PaperclipIcon size={14} style={{ width: 14, height: 14 }} />
    </Button>
  );
}

const AttachmentsButton = memo(PureAttachmentsButton);

function PureModelSelectorCompact({
  selectedModelId,
  onModelChange,
}: {
  selectedModelId: string;
  onModelChange?: (modelId: string) => void;
}) {
  const [optimisticModelId, setOptimisticModelId] = useState(selectedModelId);

  useEffect(() => {
    setOptimisticModelId(selectedModelId);
  }, [selectedModelId]);

  const selectedModel = chatModels.find(
    (model) => model.id === optimisticModelId
  );

  return (
    <PromptInputModelSelect
      onValueChange={(modelName) => {
        const model = chatModels.find((m) => m.name === modelName);
        if (model) {
          setOptimisticModelId(model.id);
          onModelChange?.(model.id);
          startTransition(() => {
            saveChatModelAsCookie(model.id);
          });
        }
      }}
      value={selectedModel?.name}
    >
      <Trigger asChild>
        <Button className="h-8 px-2" variant="ghost">
          <CpuIcon size={16} />
          <span className="hidden font-medium text-xs sm:block">
            {selectedModel?.name}
          </span>
          <ChevronDownIcon size={16} />
        </Button>
      </Trigger>
      <PromptInputModelSelectContent className="min-w-[260px] p-0">
        <div className="flex flex-col gap-px">
          {chatModels.map((model) => (
            <SelectItem key={model.id} value={model.name}>
              <div className="truncate font-medium text-xs">{model.name}</div>
              <div className="mt-px truncate text-[10px] text-muted-foreground leading-tight">
                {model.description}
              </div>
            </SelectItem>
          ))}
        </div>
      </PromptInputModelSelectContent>
    </PromptInputModelSelect>
  );
}

const ModelSelectorCompact = memo(PureModelSelectorCompact);

function PureStopButton({
  stop,
  setMessages,
}: {
  stop: () => void;
  setMessages: UseChatHelpers<ChatMessage>["setMessages"];
}) {
  return (
    <Button
      className="size-7 rounded-full bg-foreground p-1 text-background transition-colors duration-200 hover:bg-foreground/90 disabled:bg-muted disabled:text-muted-foreground"
      data-testid="stop-button"
      onClick={(event) => {
        event.preventDefault();
        stop();
        setMessages((messages) => messages);
      }}
    >
      <StopIcon size={14} />
    </Button>
  );
}

const StopButton = memo(PureStopButton);

function PureVoiceRecordButton({
  status,
  onTranscript,
}: {
  status: UseChatHelpers<ChatMessage>["status"];
  onTranscript: (text: string) => void;
}) {
  const [isRecording, setIsRecording] = useState(false);

  const handleClick = () => {
    if (isRecording) {
      // 녹음 중지
      setIsRecording(false);
      toast.info("음성 녹음이 중지되었습니다.");
      // TODO: 실제 음성 인식 구현 시 여기서 처리
    } else {
      // 녹음 시작
      setIsRecording(true);
      toast.info("음성 녹음을 시작합니다...");
      // TODO: 실제 음성 인식 구현 시 여기서 처리
    }
  };

  return (
    <Button
      className={cn(
        "aspect-square h-8 rounded-lg p-1 transition-colors",
        isRecording
          ? "bg-red-500 text-white hover:bg-red-600 animate-pulse"
          : "hover:bg-accent"
      )}
      data-testid="voice-record-button"
      disabled={status !== "ready"}
      onClick={(event) => {
        event.preventDefault();
        handleClick();
      }}
      variant="ghost"
    >
      <MicrophoneIcon size={14} />
    </Button>
  );
}

const VoiceRecordButton = memo(PureVoiceRecordButton);
