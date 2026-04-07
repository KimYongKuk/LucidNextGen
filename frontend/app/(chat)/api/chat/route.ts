import { generateUUID } from "@/lib/utils";
import { type PostRequestBody, postRequestBodySchema } from "./schema";
import { ChatSDKError } from "@/lib/errors";
import { createUIMessageStream, JsonToSseTransformStream } from "ai";
import type { ChatMessage } from "@/lib/types";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

// 백엔드 URL 설정
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

/**
 * Get user ID for server-side API routes
 * SSO 쿠키(empno)에서만 읽음 - 인증 필수
 */
const getUserId = (request: Request): string | null => {
  const cookieHeader = request.headers.get("cookie") || "";
  const empnoCookie = cookieHeader
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith("empno="));
  return empnoCookie?.split("=")[1] || null;
};

export async function POST(request: Request) {
  let requestBody: PostRequestBody;

  try {
    const json = await request.json();
    requestBody = postRequestBodySchema.parse(json);
  } catch (error) {
    return new ChatSDKError("bad_request:api").toResponse();
  }

  const userId = getUserId(request);
  if (!userId) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
  // Use session_id from request body if provided, otherwise generate new one
  const sessionId = requestBody.session_id || generateUUID();

  try {
    const { messages, message } = requestBody;
    let content = "";

    if (messages && Array.isArray(messages) && messages.length > 0) {
      const lastMessage = messages[messages.length - 1];
      content = lastMessage.content;
    } else if (message) {
      if (message.parts && Array.isArray(message.parts)) {
        content = message.parts
          .filter((part: any) => part.type === "text")
          .map((part: any) => part.text)
          .join("\n");
      } else {
        content = message.content || "";
      }
    }

    if (!content) {
      throw new Error("No message content found");
    }

    console.log("[ROUTE] Creating UI message stream");

    const uiStream = createUIMessageStream<ChatMessage>({
      execute: async ({ writer }) => {
        console.log("[ROUTE] Stream execute started");

        // Create assistant message
        const messageId = generateUUID();
        const assistantMessage: ChatMessage = {
          id: messageId,
          role: "assistant",
          parts: [{ type: "text", text: "" }],
          createdAt: new Date(),
        };

        // Write initial message
        writer.write({
          type: "data-appendMessage",
          data: JSON.stringify(assistantMessage),
        });
        console.log("[ROUTE] Sent initial assistant message");

        try {
          console.log("[ROUTE] Fetching backend...");
          const backendResponse = await fetch(
            `${BACKEND_URL}/api/v1/chat/message/stream`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                message: content,
                user_id: userId,
                session_id: sessionId,
                chat_mode: "normal",
              }),
            }
          );

          console.log("[ROUTE] Backend response status:", backendResponse.status);

          if (!backendResponse.ok) {
            const errorText = `Backend error: ${backendResponse.statusText}`;
            console.error("[ROUTE]", errorText);
            writer.write({
              type: "text-delta",
              delta: errorText,
              id: generateUUID(),
            });
            return;
          }

          const reader = backendResponse.body?.getReader();
          if (!reader) {
            console.error("[ROUTE] No reader available");
            writer.write({
              type: "text-delta",
              delta: "No reader available",
              id: generateUUID(),
            });
            return;
          }

          console.log("[ROUTE] Reading stream...");
          const decoder = new TextDecoder();
          let buffer = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              console.log("[ROUTE] Stream done");
              break;
            }

            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;
            const lines = buffer.split("\n\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                try {
                  const jsonStr = line.slice(6).trim();
                  if (!jsonStr) continue;

                  const data = JSON.parse(jsonStr);
                  console.log("[ROUTE] Backend stream data:", data);

                  if (data.type === "content" && data.chunk) {
                    console.log("[ROUTE] Writing text delta:", data.chunk);
                    writer.write({
                      type: "text-delta",
                      delta: data.chunk,
                      id: generateUUID(),
                    });
                  } else if (data.error) {
                    console.error("[ROUTE] Backend error:", data.error);
                    const errorMessage =
                      typeof data.error === "string"
                        ? data.error
                        : JSON.stringify(data.error);
                    writer.write({
                      type: "text-delta",
                      delta: `Error: ${errorMessage}`,
                      id: generateUUID(),
                    });
                  }
                } catch (e) {
                  console.error("[ROUTE] Error parsing backend response:", e);
                }
              }
            }
          }
        } catch (error) {
          // AbortError는 사용자가 중단한 것이므로 에러 표시하지 않음
          if (error instanceof Error && (error.name === 'AbortError' || error.message.includes('aborted'))) {
            console.log("[ROUTE] Stream aborted by client");
          } else {
            console.error("[ROUTE] Stream processing error:", error);
            writer.write({
              type: "text-delta",
              delta: `Stream error: ${String(error)}`,
              id: generateUUID(),
            });
          }
        }

        console.log("[ROUTE] Execute completed");
      },
    });

    const response = uiStream.pipeThrough(new JsonToSseTransformStream());

    return new Response(response, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    console.error("Unhandled error in chat API:", error);
    return new ChatSDKError("offline:chat").toResponse();
  }
}

export async function DELETE(request: Request) {
  return new Response("Not implemented", { status: 501 });
}
