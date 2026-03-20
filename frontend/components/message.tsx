"use client";
import type { UseChatHelpers } from "@ai-sdk/react";
import equal from "fast-deep-equal";
import { memo, useEffect, useState } from "react";
import type { ChatMessage } from "@/lib/types";
// Mock Vote type since DB is removed
type Vote = {
  chatId: string;
  messageId: string;
  isUpvoted: boolean;
};
import { cn, sanitizeText } from "@/lib/utils";
import { useDataStream } from "./data-stream-provider";
import { DocumentToolResult } from "./document";
import { DocumentPreview } from "./document-preview";
import { MessageContent } from "./elements/message";
import { Response } from "./elements/response";
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
} from "./elements/tool";

import { MessageActions } from "./message-actions";
import { MessageEditor } from "./message-editor";
import { MessageReasoning } from "./message-reasoning";
import { PreviewAttachment } from "./preview-attachment";
import { Weather } from "./weather";
import { SourcesCarousel } from "./sources-carousel";
import { CorpSourcesCarousel } from "./corp-sources-carousel";
import { YouTubeCard } from "./youtube-card";
import { YouTubeModal } from "./youtube-modal";
import { ChartDisplay } from "./chart-display";
import { SVGDisplay } from "./svg-display";

// Separate component to handle YouTube summary with card and modal
const YoutubeSummaryCard = ({ summary }: { summary: any }) => {
  const [showModal, setShowModal] = useState(false);

  return (
    <>
      {/* Border line before the YouTube card */}
      <div className="my-4 border-t border-border/50" />
      <div className="max-w-md">
        <YouTubeCard
          title={summary.title}
          videoId={summary.video_id}
          summary={summary.summary}
          onClick={() => setShowModal(true)}
        />
      </div>
      <YouTubeModal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        videoUrl={summary.original_link}
        videoId={summary.video_id}
        title={summary.title}
        summary={summary.summary}
        insight={summary.insight}
        keywords={summary.keywords}
        segments={summary.segments}
      />
    </>
  );
};

const PurePreviewMessage = ({
  chatId,
  message,
  vote,
  isLoading,
  setMessages,
  regenerate,
  isReadonly,
  requiresScrollPadding: _requiresScrollPadding,
}: {
  chatId: string;
  message: ChatMessage;
  vote: Vote | undefined;
  isLoading: boolean;
  setMessages: UseChatHelpers<ChatMessage>["setMessages"];
  regenerate: UseChatHelpers<ChatMessage>["regenerate"];
  isReadonly: boolean;
  requiresScrollPadding: boolean;
}) => {
  const [mode, setMode] = useState<"view" | "edit">("view");

  const attachmentsFromMessage = message.parts.filter(
    (part) => part.type === "file"
  );

  useDataStream();

  return (
    <div
      className="group/message fade-in w-full animate-in duration-200"
      data-role={message.role}
      data-testid={`message-${message.role}`}
    >
      <div
        className={cn("flex w-full items-start gap-2 md:gap-3", {
          "justify-end": message.role === "user" && mode !== "edit",
          "justify-start": message.role === "assistant",
        })}
      >
        {message.role === "assistant" && (
          <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full">
            <img
              src={isLoading ? "/logo.svg" : "/logo.png"}
              alt="Lucid AI"
              className="size-8"
            />
          </div>
        )}

        <div
          className={cn("flex flex-col", {
            "gap-2 md:gap-4": message.parts?.some(
              (p) => p.type === "text" && p.text?.trim()
            ),
            "w-full":
              (message.role === "assistant" &&
                message.parts?.some(
                  (p) => p.type === "text" && p.text?.trim()
                )) ||
              mode === "edit",
            "max-w-[calc(100%-2.5rem)] sm:max-w-[min(fit-content,80%)]":
              message.role === "user" && mode !== "edit",
          })}
        >
          {attachmentsFromMessage.length > 0 && (
            <div
              className="flex flex-row justify-end gap-2"
              data-testid={"message-attachments"}
            >
              {attachmentsFromMessage.map((attachment) => (
                <PreviewAttachment
                  attachment={{
                    name: attachment.filename ?? "file",
                    contentType: attachment.mediaType,
                    url: attachment.url,
                  }}
                  key={attachment.url}
                />
              ))}
            </div>
          )}

          {message.parts?.map((part, index) => {
            const { type } = part;
            const key = `message-${message.id}-part-${index}`;

            if (type === "reasoning" && part.text?.trim().length > 0) {
              return (
                <MessageReasoning
                  isLoading={isLoading}
                  key={key}
                  reasoning={part.text}
                />
              );
            }

            if (type === "text") {
              if (mode === "view") {
                const isAssistantLoadingPlaceholder =
                  message.role === "assistant" &&
                  isLoading &&
                  !(part.text?.trim()?.length);

                if (isAssistantLoadingPlaceholder) {
                  return (
                    <div key={key}>
                      <MessageContent className="w-fit rounded-2xl px-3 py-2 text-left text-muted-foreground">
                        <LoadingPlaceholderText />
                      </MessageContent>
                    </div>
                  );
                }

                return (
                  <div key={key}>
                    {/* <div className="text-xs text-red-500 font-mono p-2 border border-red-200 my-2">
                      DEBUG PART: {JSON.stringify(part)}
                    </div> */}
                    <MessageContent
                      className={cn({
                        "w-fit break-words rounded-xl px-2.5 py-1 text-left bg-[#B85C38] dark:bg-[#8B4513] text-white shadow-sm":
                          message.role === "user",
                        "bg-transparent px-0 py-0 text-left":
                          message.role === "assistant",
                      })}
                      data-testid="message-content"
                    >
                      {message.role === "user" ? (
                        <div className="whitespace-pre-wrap">{sanitizeText(part.text)}</div>
                      ) : (
                        <Response isStreaming={isLoading} workerName={message.workerName}>{sanitizeText(part.text)}</Response>
                      )}
                    </MessageContent>
                  </div>
                );
              }

              if (mode === "edit") {
                return (
                  <div
                    className="flex w-full flex-row items-start gap-3"
                    key={key}
                  >
                    <div className="size-8" />
                    <div className="min-w-0 flex-1">
                      <MessageEditor
                        key={message.id}
                        message={message}
                        regenerate={regenerate}
                        setMessages={setMessages}
                        setMode={setMode}
                      />
                    </div>
                  </div>
                );
              }
            }

            if (type === "tool-getWeather") {
              const { toolCallId, state } = part;

              return (
                <Tool defaultOpen={true} key={toolCallId}>
                  <ToolHeader state={state} type="tool-getWeather" />
                  <ToolContent>
                    {state === "input-available" && (
                      <ToolInput input={part.input} />
                    )}
                    {state === "output-available" && (
                      <ToolOutput
                        errorText={undefined}
                        output={<Weather weatherAtLocation={part.output} />}
                      />
                    )}
                  </ToolContent>
                </Tool>
              );
            }

            if (type === "tool-createDocument") {
              const { toolCallId } = part;

              if (part.output && "error" in part.output) {
                return (
                  <div
                    className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-500 dark:bg-red-950/50"
                    key={toolCallId}
                  >
                    Error creating document: {String(part.output.error)}
                  </div>
                );
              }

              return (
                <DocumentPreview
                  isReadonly={isReadonly}
                  key={toolCallId}
                  result={part.output}
                />
              );
            }

            if (type === "tool-updateDocument") {
              const { toolCallId } = part;

              if (part.output && "error" in part.output) {
                return (
                  <div
                    className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-500 dark:bg-red-950/50"
                    key={toolCallId}
                  >
                    Error updating document: {String(part.output.error)}
                  </div>
                );
              }

              return (
                <div className="relative" key={toolCallId}>
                  <DocumentPreview
                    args={{ ...part.output, isUpdate: true }}
                    isReadonly={isReadonly}
                    result={part.output}
                  />
                </div>
              );
            }

            if (type === "tool-requestSuggestions") {
              const { toolCallId, state } = part;

              return (
                <Tool defaultOpen={true} key={toolCallId}>
                  <ToolHeader state={state} type="tool-requestSuggestions" />
                  <ToolContent>
                    {state === "input-available" && (
                      <ToolInput input={part.input} />
                    )}
                    {state === "output-available" && (
                      <ToolOutput
                        errorText={undefined}
                        output={
                          "error" in part.output ? (
                            <div className="rounded border p-2 text-red-500">
                              Error: {String(part.output.error)}
                            </div>
                          ) : (
                            <DocumentToolResult
                              isReadonly={isReadonly}
                              result={part.output}
                              type="request-suggestions"
                            />
                          )
                        }
                      />
                    )}
                  </ToolContent>
                </Tool>
              );
            }

            // @ts-ignore - Custom type for sources
            if (type === "sources") {
              const sourcesPart = part as any;
              return <SourcesCarousel key={key} sources={sourcesPart.sources} />;
            }

            // @ts-ignore - Custom type for corp sources
            if (type === "corp-sources") {
              const corpSourcesPart = part as any;
              return <CorpSourcesCarousel key={key} sources={corpSourcesPart.sources} />;
            }

            // @ts-ignore - Custom type for youtube summary
            if (type === "youtube-summary") {
              const youtubePart = part as any;
              return <YoutubeSummaryCard key={key} summary={youtubePart.summary} />;
            }

            // @ts-ignore - Custom type for chart data
            if (type === "chart-data") {
              const chartPart = part as any;
              return <ChartDisplay key={key} chartData={chartPart.chartData} />;
            }

            // @ts-ignore - Custom type for SVG visual
            if (type === "svg-visual") {
              const svgPart = part as any;
              return <SVGDisplay key={key} svgData={svgPart.svgData} />;
            }

            return null;
          })}

          {!isReadonly && (
            <MessageActions
              chatId={chatId}
              isLoading={isLoading}
              key={`action-${message.id}`}
              message={message}
              setMode={setMode}
              vote={vote}
            />
          )}
        </div>
      </div>
    </div>
  );
};

export const PreviewMessage = memo(
  PurePreviewMessage,
  (prevProps, nextProps) => {
    if (prevProps.isLoading !== nextProps.isLoading) {
      return false;
    }
    if (prevProps.message.id !== nextProps.message.id) {
      return false;
    }
    if (prevProps.requiresScrollPadding !== nextProps.requiresScrollPadding) {
      return false;
    }
    if (!equal(prevProps.message.parts, nextProps.message.parts)) {
      return false;
    }
    if (!equal(prevProps.vote, nextProps.vote)) {
      return false;
    }

    return true; // props가 모두 같으면 리렌더링 스킵
  }
);

const LoadingPlaceholderText = () => {
  const text = "루시드가 생각을 정리하고 있습니다. 잠시만 기다려주세요.";
  const [displayed, setDisplayed] = useState("");

  useEffect(() => {
    let i = 0;
    const timer = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) clearInterval(timer);
    }, 60);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="relative inline-flex items-center">
      <span className="animate-pulse">{displayed}</span>
      {displayed.length < text.length && (
        <span className="ml-0.5 inline-block w-[2px] h-3.5 bg-muted-foreground/60 animate-pulse" />
      )}
    </div>
  );
};

export const ThinkingMessage = () => {
  const text = "Thinking...";
  const [displayed, setDisplayed] = useState("");

  useEffect(() => {
    let i = 0;
    const timer = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) clearInterval(timer);
    }, 80);
    return () => clearInterval(timer);
  }, []);

  return (
    <div
      className="group/message fade-in w-full animate-in duration-300"
      data-role="assistant"
      data-testid="message-assistant-loading"
    >
      <div className="flex items-start justify-start gap-3">
        <div className="-mt-1 flex size-8 shrink-0 items-center justify-center rounded-full">
          <img src="/logo.svg" alt="Lucid AI" className="size-8" />
        </div>

        <div className="flex w-full flex-col gap-2 md:gap-4">
          <div className="flex items-center gap-1 p-0 text-muted-foreground text-sm">
            <span className="animate-pulse">{displayed}</span>
            {displayed.length < text.length && (
              <span className="ml-0.5 inline-block w-[2px] h-3.5 bg-muted-foreground/60 animate-pulse" />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
