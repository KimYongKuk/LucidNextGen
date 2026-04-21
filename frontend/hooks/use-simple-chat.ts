"use client";

import { useState, useCallback, useRef } from 'react';
import type { ChatMessage } from '@/lib/types';
import { getUserId } from '@/lib/utils';
import { getApiUrl } from '@/lib/api/config';

// 고유 ID 생성 함수
const generateId = (): string => {
  const uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
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
  chatMode?: string;  // 'normal' | 'outline_embed' 등
  onData?: (data: any) => void;
  onFinish?: () => void;
  onError?: (error: Error) => void;
  generateId?: () => string;
  workspaceId?: string | null;  // UUID string
  userId?: string;  // 외부에서 주입 (embed 등 SSO 쿠키 없는 환경)
  widgetAuthToken?: string;  // 그룹웨어 위젯 암호화 토큰 (embed 전용)
}

export function useSimpleChat({
  id: sessionId,
  messages: initialMessages,
  chatMode = 'normal',
  onData,
  onFinish,
  onError,
  generateId: customGenerateId = generateId,
  workspaceId,
  userId: externalUserId,
  widgetAuthToken,
}: UseSimpleChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [status, setStatus] = useState<'ready' | 'streaming' | 'submitted'>('ready');
  const [followUpSuggestions, setFollowUpSuggestions] = useState<string[] | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const userId = externalUserId || getUserId() || "anonymous";
  const userIdRef = useRef(userId);
  userIdRef.current = userId;
  const chatModeRef = useRef(chatMode);
  chatModeRef.current = chatMode;

  const sendMessage = useCallback(async (message: Omit<ChatMessage, 'id' | 'createdAt'>) => {
    // 이전 팔로우업 제안 초기화
    setFollowUpSuggestions(null);

    // 사용자 메시지 추가
    const userMessage: ChatMessage = {
      ...message,
      id: customGenerateId(),
      createdAt: new Date(),
    } as ChatMessage;

    setMessages(prev => [...prev, userMessage]);
    setStatus('streaming');

    // Assistant 메시지 ID 미리 생성
    const assistantMessageId = customGenerateId();

    try {
      let hasCompleted = false;
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
                stored_filename: part.storedFilename || null,
              };
            }
          }
          return null;
        })
        .filter((img): img is { media_type: string; base64_data: string; stored_filename: string | null } => !!img && !!img.base64_data) || [];

      // 현재 메시지 히스토리 구성 (현재 사용자 메시지 제외)
      // 최대 15회의 대화만 전송 (토큰 관리 + 워크스페이스 메모리로 이전 대화 보완)
      const MAX_CONVERSATION_TURNS = 15;
      const MAX_HISTORY_MESSAGES = MAX_CONVERSATION_TURNS * 2; // user + assistant 쌍

      // 최근 메시지부터 최대 개수만큼만 선택
      const recentMessages = messages.slice(-MAX_HISTORY_MESSAGES);

      const messageHistory = recentMessages.map((msg) => {
        // parts에서 텍스트만 추출
        const textContent = msg.parts
          ?.filter((part: any) => part.type === 'text')
          .map((part: any) => part.text)
          .join('\n') || '';

        // user 메시지에 이미지가 포함된 경우 멀티모달 content 구성
        const imageParts = msg.role === 'user' ? msg.parts
          ?.filter((part: any) => part.type === 'file' && part.mediaType?.startsWith('image/'))
          .map((part: any) => {
            if (part.url?.startsWith('data:')) {
              const matches = part.url.match(/^data:(.*?);base64,(.+)$/);
              if (matches) {
                return {
                  type: 'image',
                  source: {
                    type: 'base64',
                    media_type: matches[1],
                    data: matches[2],
                  },
                };
              }
            }
            return null;
          })
          .filter(Boolean) || [] : [];

        if (imageParts.length > 0) {
          console.log(`[HISTORY] Including ${imageParts.length} image(s) in history message`);
          return {
            role: msg.role,
            content: [
              ...imageParts,
              { type: 'text', text: textContent },
            ],
          };
        }

        return {
          role: msg.role,
          content: textContent,
        };
      });

      // 백엔드로 스트리밍 요청
      abortControllerRef.current = new AbortController();

      const baseUrl = getApiUrl();
      const apiUrl = `${baseUrl}/api/v1/chat/message/stream`;

      const response = await fetch(apiUrl, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(widgetAuthToken ? { 'X-Widget-Auth': widgetAuthToken } : {}),
        },
        body: JSON.stringify({
          message: content,
          chat_mode: chatModeRef.current,
          session_id: sessionId,
          user_id: userIdRef.current,
          images: imageFiles.length > 0 ? imageFiles : null,
          message_history: messageHistory.length > 0 ? messageHistory : null,
          workspace_id: workspaceId,
          // gosso_cookie 추출 — GOSSOcookie(LFON 원본) 우선, 없으면 gosso(middleware 세팅) 폴백
          // LFON이 GOSSOcookie를 `.landf.co.kr` 도메인으로 세팅하면 iframe에서도 직접 읽힘 →
          // SSO URL param 경로 안 거쳐도 그룹웨어 로그인 상태만으로 쓰기 작업 가능
          ...(typeof document !== 'undefined' && (() => {
            const m1 = document.cookie.match(/(?:^|;\s*)GOSSOcookie=([^;]+)/);
            const m2 = document.cookie.match(/(?:^|;\s*)gosso=([^;]+)/);
            const val = m1?.[1] || m2?.[1];
            return val ? { gosso_cookie: val } : {};
          })()),
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
      let currentToolStatus = ''; // 현재 표시 중인 Tool 상태 메시지 (임시)
      let sources: any[] = []; // Tavily 검색 출처 (매 요청마다 초기화)
      let youtubeSummary: any = null; // YouTube 요약 (매 요청마다 초기화)
      let corpSources: any[] = []; // Corp 문서 출처 (매 요청마다 초기화)
      let chartData: any = null; // 차트 데이터 (매 요청마다 초기화)
      let svgData: any = null; // SVG 시각화 데이터 (매 요청마다 초기화)
      let workerName: string = ''; // 인텐트 분류 결과 워커 이름

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

                  // 대기 상태 메시지 처리 (세마포어 대기)
                  if (data.type === 'waiting') {
                    const waitingMessage = data.message || '다른 사용자의 요청을 처리 중입니다. 잠시만 기다려주세요...';
                    currentToolStatus = `\n\n__WAITING__:${waitingMessage}__END__\n\n`;

                    const currentContent = allChunks.join('') + currentToolStatus;
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

                  // 대기 완료 메시지 처리
                  if (data.type === 'waiting_complete') {
                    // 대기 상태 메시지 제거
                    currentToolStatus = '';
                  }

                  // 보안 차단 이벤트 (Security Guard)
                  if (data.type === 'security_blocked') {
                    const blockMsg = data.message || '요청이 차단되었습니다.';
                    console.warn('[SECURITY_BLOCKED]', {
                      action: data.action,
                      threat_type: data.threat_type,
                      severity: data.severity,
                      expires_at: data.expires_at,
                    });
                    allChunks.push(blockMsg);
                    setMessages(prev => prev.map(msg =>
                      msg.id === assistantMessageId
                        ? {
                          ...msg,
                          parts: [{ type: 'text', text: blockMsg }],
                        }
                        : msg
                    ));
                  }

                  // 처리 시작 메시지
                  if (data.type === 'processing_start') {
                    // 대기 상태 메시지 제거
                    currentToolStatus = '';
                    const currentContent = allChunks.join('');
                    setMessages(prev => prev.map(msg =>
                      msg.id === assistantMessageId
                        ? {
                          ...msg,
                          parts: [{ type: 'text', text: currentContent }]
                        }
                        : msg
                    ));
                  }

                  // Tool 상태 메시지 처리 (애니메이션 적용 - 임시로만 표시)
                  if (data.type === 'tool_status') {
                    const toolMessage = data.message || '작업 중...';

                    // Tool 상태를 임시 변수에 저장 (allChunks에는 저장하지 않음!)
                    currentToolStatus = `\n\n__TOOL_STATUS__:${toolMessage}__END__\n\n`;

                    // 실시간 UI 업데이트 (기존 컨텐츠 + 임시 Tool 상태)
                    const currentContent = allChunks.join('') + currentToolStatus;
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

                  // Tavily 검색 출처 처리 (저장만, 스트리밍 완료 후 표시)
                  if (data.type === 'search_sources' && data.sources) {
                    sources = data.sources;
                    // 출처는 저장만 하고 스트리밍 완료 시 표시
                  }

                  // YouTube 요약 처리 (저장만, 스트리밍 완료 후 표시)
                  if (data.type === 'youtube_summary' && data.summary) {
                    youtubeSummary = data.summary;
                    // YouTube 요약은 저장만 하고 스트리밍 완료 시 표시
                  }

                  // Corp 문서 출처 처리 (저장만, 스트리밍 완료 후 표시)
                  if (data.type === 'corp_sources' && data.sources) {
                    corpSources = data.sources;
                    // Corp 출처는 저장만 하고 스트리밍 완료 시 표시
                  }

                  // 차트 데이터 처리 (저장만, 스트리밍 완료 후 표시)
                  if (data.type === 'chart_data' && data.chart) {
                    chartData = data.chart;
                    // 차트는 저장만 하고 스트리밍 완료 시 표시
                  }

                  // SVG 시각화 데이터 처리 (저장만, 스트리밍 완료 후 표시)
                  if (data.type === 'svg_visual' && data.svg_data) {
                    svgData = data.svg_data;
                  }

                  // Intent 분류 결과 처리 (워커 이름 캡처)
                  if (data.type === 'intent_classified' && data.worker) {
                    workerName = data.worker;
                  }

                  // Planner-Executor CoT 이벤트 처리 — taskCoTs 누적
                  const mergeTaskCoT = (taskId: string, updater: (prev: any) => any) => {
                    setMessages(prev => prev.map(msg => {
                      if (msg.id !== assistantMessageId) return msg;
                      const prevCoTs = (msg as any).taskCoTs || {};
                      const existing = prevCoTs[taskId] || {
                        task_id: taskId,
                        worker: '',
                        goal: '',
                        events: [],
                        status: 'started',
                      };
                      return { ...msg, taskCoTs: { ...prevCoTs, [taskId]: updater(existing) } };
                    }));
                  };

                  if (data.type === 'task_started' && data.task_id) {
                    mergeTaskCoT(data.task_id, (prev) => ({
                      ...prev,
                      worker: data.worker || prev.worker,
                      goal: data.goal || prev.goal,
                      status: 'started',
                    }));
                  }

                  if (data.type === 'task_thinking' && data.task_id && data.content) {
                    // pre-tool reasoning chunk 누적
                    mergeTaskCoT(data.task_id, (prev) => {
                      // 마지막 이벤트가 thinking이면 이어붙이기 (chunk 병합으로 이벤트 수 억제)
                      const events = [...prev.events];
                      const last = events[events.length - 1];
                      if (last && last.kind === 'thinking') {
                        events[events.length - 1] = {
                          ...last,
                          content: last.content + data.content,
                        };
                      } else {
                        events.push({ kind: 'thinking', content: data.content, ts: Date.now() });
                      }
                      return { ...prev, events };
                    });
                  }

                  // executor_done 이벤트 수신 시 — 모든 thinking 이벤트 정제
                  // (HTML 코멘트 마커 제거, 과도 공백 축약)
                  if (data.type === 'executor_done') {
                    setMessages(prev => prev.map(msg => {
                      if (msg.id !== assistantMessageId) return msg;
                      const prevCoTs = (msg as any).taskCoTs || {};
                      const cleanedCoTs: any = {};
                      for (const [tid, cot] of Object.entries(prevCoTs)) {
                        const c: any = cot;
                        cleanedCoTs[tid] = {
                          ...c,
                          events: (c.events || []).map((ev: any) => {
                            if (ev.kind !== 'thinking') return ev;
                            // <!--FOLLOW_UP:...-->, <!--HANDOFF:...-->, <!--NO_RESULTS--> 등 마커 제거
                            let cleaned = ev.content.replace(/<!--[A-Z_]+:?[^>]*-->/g, '');
                            // 3줄 이상 연속 공백 → 2줄로 축약
                            cleaned = cleaned.replace(/\n{3,}/g, '\n\n').trim();
                            return { ...ev, content: cleaned };
                          }).filter((ev: any) => {
                            // 내용이 완전히 빈 thinking 이벤트는 제거
                            if (ev.kind === 'thinking') return ev.content.trim().length > 0;
                            return true;
                          }),
                        };
                      }
                      return { ...msg, taskCoTs: cleanedCoTs };
                    }));
                  }

                  if (data.type === 'tool_status' && data.task_id) {
                    // task_narration으로 온 tool_status (Haiku 내레이션)
                    mergeTaskCoT(data.task_id, (prev) => ({
                      ...prev,
                      events: [
                        ...prev.events,
                        { kind: 'narration', tool: data.tool || '', content: data.message || '', ts: Date.now() },
                      ],
                    }));
                    // 기존 전역 tool_status도 그대로 표시 (inline __TOOL_STATUS__ 마커) → 계속 아래 기존 핸들러 흘러가도록
                  }

                  if (data.type === 'task_completed' && data.task_id) {
                    mergeTaskCoT(data.task_id, (prev) => ({
                      ...prev,
                      status: 'completed',
                      elapsed_ms: data.elapsed_ms,
                      result_preview: data.result_preview,
                    }));
                  }

                  if (data.type === 'task_failed' && data.task_id) {
                    mergeTaskCoT(data.task_id, (prev) => ({
                      ...prev,
                      status: 'failed',
                      elapsed_ms: data.elapsed_ms,
                      error: data.error,
                    }));
                  }

                  if (data.type === 'task_skipped' && data.task_id) {
                    mergeTaskCoT(data.task_id, (prev) => ({
                      ...prev,
                      status: 'skipped',
                      error: data.reason,
                    }));
                  }

                  if (data.type === 'task_awaiting_confirm' && data.task_id) {
                    mergeTaskCoT(data.task_id, (prev) => ({
                      ...prev,
                      worker: data.worker || prev.worker,
                      goal: data.goal || prev.goal,
                      status: 'awaiting_confirm',
                    }));
                  }

                  // Follow-up suggestions 처리
                  if (data.type === 'follow_up_suggestions' && data.suggestions) {
                    setFollowUpSuggestions(data.suggestions);
                  }

                  // 모델 Fallback 알림 처리
                  if (data.type === 'model_fallback') {
                    const fallbackMessage = data.message || `${data.model}로 전환되었습니다.`;
                    // Fallback 알림을 임시 상태로 표시 (tool_status와 유사)
                    currentToolStatus = `\n\n__FALLBACK__:${fallbackMessage}__END__\n\n`;

                    const currentContent = allChunks.join('') + currentToolStatus;
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

                  // 콘텐츠 청크 처리
                  if (data.type === 'content' && data.chunk) {
                    allChunks.push(data.chunk);

                    // Tool 상태 메시지가 있으면 제거 (실제 응답이 오기 시작하면 Tool 상태 삭제)
                    if (currentToolStatus && data.chunk.trim()) {
                      currentToolStatus = '';
                    }

                    // 실시간 UI 업데이트 - workerName은 메시지 객체에 별도 저장 (텍스트 마커 삽입 제거)
                    const currentContent = allChunks.join('');
                    setMessages(prev => prev.map(msg =>
                      msg.id === assistantMessageId
                        ? {
                          ...msg,
                          workerName: workerName || msg.workerName,
                          parts: [{ type: 'text', text: currentContent }]
                        }
                        : msg
                    ));

                    await new Promise(resolve => setTimeout(resolve, 0));
                  }

                  // 완료 체크
                  if (data.complete) {
                    hasCompleted = true;

                    // 스트리밍 완료 후 최종 parts 구성
                    // 팔로우업 마커 strip + 텍스트/차트/출처/Corp출처/YouTube 요약 조합
                    const rawContent = allChunks.join('');
                    const cleanedContent = rawContent.replace(/\s*<!--FOLLOW_UP:[\s\S]*?-->\s*$/, '').trimEnd();

                    const finalParts: any[] = [{ type: 'text', text: cleanedContent }];
                    if (chartData) {
                      finalParts.push({ type: 'chart-data', chartData });
                    }
                    if (svgData) {
                      finalParts.push({ type: 'svg-visual', svgData });
                    }
                    if (sources.length > 0) {
                      finalParts.push({ type: 'sources', sources });
                    }
                    if (corpSources.length > 0) {
                      finalParts.push({ type: 'corp-sources', sources: corpSources });
                    }
                    if (youtubeSummary) {
                      finalParts.push({ type: 'youtube-summary', summary: youtubeSummary });
                    }

                    setMessages(prev => prev.map(msg =>
                      msg.id === assistantMessageId
                        ? { ...msg, workerName: workerName || msg.workerName, parts: finalParts }
                        : msg
                    ));

                    break;
                  }
                } catch (parseError) {
                  console.warn('JSON parsing failed:', line, parseError);
                }
              }

              if (hasCompleted) {
                break;
              }
            }

            if (hasCompleted) {
              break;
            }
          }
        } finally {
          reader.releaseLock();
        }
      }

      if (onFinish) {
        onFinish();
        hasCompleted = true;
      }

    } catch (error) {
      // AbortError는 사용자가 중단한 것이므로 에러 표시하지 않음
      const isAbort = error instanceof DOMException && error.name === 'AbortError';
      if (isAbort) {
        console.log('Chat stream aborted by user');
      } else {
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
      }
    } finally {
      setStatus('ready');
      abortControllerRef.current = null;
    }
  }, [sessionId, workspaceId, onData, onFinish, onError, customGenerateId]);

  const stop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setStatus('ready');
    }
  }, []);

  const regenerate = useCallback(async () => {
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
      await sendMessage(lastUserMessage);
    }
  }, [messages, sendMessage]);

  const resumeStream = useCallback(async () => {
    // 현재 구현에서는 resume 기능 불필요 (자동 완료)
  }, []);

  return {
    messages,
    setMessages,
    sendMessage,
    status,
    stop,
    regenerate,
    resumeStream,
    followUpSuggestions,
  };
}
