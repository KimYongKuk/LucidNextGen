"use client";

import { useState, useCallback, useRef } from 'react';
import type { ChatMessage } from '@/lib/types';

// 동적 API URL 생성 함수
const getApiUrl = () => {
  if (typeof window !== 'undefined') {
    const currentHost = window.location.hostname;
    const isLocalhost = currentHost === 'localhost' || currentHost === '127.0.0.1';

    if (isLocalhost) {
      return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    } else {
      const protocol = window.location.protocol;
      return `${protocol}//${currentHost}:8000`;
    }
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
};

// 고유 ID 생성 함수
const generateId = (): string => {
  const uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c == 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });

  const timestamp = Date.now().toString(36);
  const counter = Math.random().toString(36).substring(2, 9);
  return `${uuid}-${timestamp}-${counter}`;
};

interface UseSimpleChatOptions {
  id: string;
  messages: ChatMessage[];
  onData?: (data: any) => void;
  onFinish?: () => void;
  onError?: (error: Error) => void;
  generateId?: () => string;
}

export function useSimpleChat({
  id: sessionId,
  messages: initialMessages,
  onData,
  onFinish,
  onError,
  generateId: customGenerateId = generateId,
}: UseSimpleChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [status, setStatus] = useState<'ready' | 'streaming' | 'submitted'>('ready');
  const abortControllerRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (message: ChatMessage) => {
    // 사용자 메시지 추가
    const userMessage: ChatMessage = {
      ...message,
      id: customGenerateId(),
      createdAt: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setStatus('streaming');

    // Assistant 메시지 ID 미리 생성
    const assistantMessageId = customGenerateId();

    try {
      // 메시지 content 추출
      const content = message.parts
        ?.filter((part: any) => part.type === 'text')
        .map((part: any) => part.text)
        .join('\n') || '';

      if (!content) {
        throw new Error('No message content');
      }

      // 이미지 파일 추출 (data URL에서 base64 추출)
      const imageFiles = message.parts
        ?.filter((part: any) => part.type === 'file' && part.mediaType?.startsWith('image/'))
        .map((part: any) => {
          // data URL에서 base64 데이터 추출
          if (part.url?.startsWith('data:')) {
            const matches = part.url.match(/^data:(.*?);base64,(.+)$/);
            if (matches) {
              return {
                media_type: matches[1],
                base64_data: matches[2],
              };
            }
          }
          return null;
        })
        .filter(Boolean) || [];

      // 현재 메시지 히스토리 구성 (현재 사용자 메시지 제외)
      // 최대 5회의 대화만 전송 (토큰 관리를 위해)
      const MAX_CONVERSATION_TURNS = 5;
      const MAX_HISTORY_MESSAGES = MAX_CONVERSATION_TURNS * 2; // user + assistant 쌍

      // 최근 메시지부터 최대 개수만큼만 선택
      const recentMessages = messages.slice(-MAX_HISTORY_MESSAGES);

      const messageHistory = recentMessages.map((msg) => {
        // parts에서 텍스트만 추출
        const textContent = msg.parts
          ?.filter((part: any) => part.type === 'text')
          .map((part: any) => part.text)
          .join('\n') || '';

        return {
          role: msg.role,
          content: textContent,
        };
      });

      // 백엔드로 스트리밍 요청
      abortControllerRef.current = new AbortController();

      const response = await fetch(`${getApiUrl()}/api/v1/chat/message/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: content,
          chat_mode: 'normal',
          session_id: sessionId,
          user_id: 'anonymous',
          images: imageFiles.length > 0 ? imageFiles : null,
          message_history: messageHistory.length > 0 ? messageHistory : null,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // 빈 어시스턴트 메시지 추가
      const initialAssistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        parts: [{ type: 'text', text: '' }],
        createdAt: new Date(),
      };
      setMessages(prev => [...prev, initialAssistantMessage]);

      // 스트리밍 데이터 수집
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let allChunks: string[] = [];

      if (reader) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;

            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (line.trim() === '') continue;

              if (line.startsWith('data: ')) {
                try {
                  const jsonStr = line.slice(6).trim();
                  if (jsonStr === '') continue;

                  const data = JSON.parse(jsonStr);

                  if (data.error) {
                    throw new Error(data.error);
                  }

                  // 타이밍 정보 처리
                  if (data.type === 'timing' && onData) {
                    onData({ type: 'data-timing', data: data });
                  }

                  // 콘텐츠 청크 처리
                  if (data.type === 'content' && data.chunk) {
                    allChunks.push(data.chunk);

                    // 실시간 UI 업데이트
                    const currentContent = allChunks.join('');
                    setMessages(prev => prev.map(msg =>
                      msg.id === assistantMessageId
                        ? {
                            ...msg,
                            parts: [{ type: 'text', text: currentContent }]
                          }
                        : msg
                    ));

                    await new Promise(resolve => setTimeout(resolve, 0));
                  }

                  // 완료 체크
                  if (data.complete) {
                    console.log('[useSimpleChat] Streaming completed');
                    if (onFinish) {
                      onFinish();
                    }
                    return;
                  }
                } catch (parseError) {
                  console.warn('JSON parsing failed:', line, parseError);
                }
              }
            }
          }
        } finally {
          reader.releaseLock();
        }
      }

    } catch (error) {
      console.error('Chat error:', error);

      // 오류 메시지로 업데이트
      setMessages(prev => prev.map(msg =>
        msg.id === assistantMessageId
          ? {
              ...msg,
              parts: [{
                type: 'text',
                text: `오류가 발생했습니다: ${error instanceof Error ? error.message : '알 수 없는 오류'}`
              }]
            }
          : msg
      ));

      if (onError && error instanceof Error) {
        onError(error);
      }
    } finally {
      setStatus('ready');
      abortControllerRef.current = null;
    }
  }, [sessionId, onData, onFinish, onError, customGenerateId]);

  const stop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setStatus('ready');
    }
  }, []);

  const regenerate = useCallback(() => {
    // 마지막 사용자 메시지 다시 전송
    const lastUserMessage = messages.filter(m => m.role === 'user').pop();
    if (lastUserMessage) {
      // 마지막 어시스턴트 응답 제거
      setMessages(prev => {
        const lastAssistantIndex = prev.map(m => m.role).lastIndexOf('assistant');
        if (lastAssistantIndex !== -1) {
          return prev.slice(0, lastAssistantIndex);
        }
        return prev;
      });

      // 재전송
      sendMessage(lastUserMessage);
    }
  }, [messages, sendMessage]);

  const resumeStream = useCallback(() => {
    // 현재 구현에서는 resume 기능 불필요 (자동 완료)
    console.log('[useSimpleChat] resumeStream called (no-op)');
  }, []);

  return {
    messages,
    setMessages,
    sendMessage,
    status,
    stop,
    regenerate,
    resumeStream,
  };
}
