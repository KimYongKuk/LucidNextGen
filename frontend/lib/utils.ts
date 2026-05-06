import type {
  CoreAssistantMessage,
  CoreToolMessage,
  UIMessage,
  UIMessagePart,
} from 'ai';
import { type ClassValue, clsx } from 'clsx';
import { formatISO } from 'date-fns';
import { twMerge } from 'tailwind-merge';
// import type { DBMessage, Document } from '@/lib/db/schema';
import { ChatSDKError, type ErrorCode } from './errors';
import type { ChatMessage, ChatTools, CustomUIDataTypes } from './types';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const fetcher = async (url: string) => {
  const response = await fetch(url);

  if (!response.ok) {
    const errorData = await response.json();
    const code = errorData.code || 'bad_request:api';
    const cause = errorData.cause || errorData.detail || 'Unknown error';
    throw new ChatSDKError(code as ErrorCode, cause);
  }

  return response.json();
};

export async function fetchWithErrorHandlers(
  input: RequestInfo | URL,
  init?: RequestInit,
) {
  try {
    const response = await fetch(input, init);

    if (!response.ok) {
      // 에러 응답이 JSON이 아닐 수 있으므로 안전하게 처리
      let errorData: any = {};
      try {
        const text = await response.text();
        errorData = JSON.parse(text);
      } catch {
        // JSON 파싱 실패 시 텍스트 그대로 사용
        errorData = {
          code: 'server_error',
          cause: `Server error: ${response.status} ${response.statusText}`,
        };
      }
      const code = errorData.code || 'bad_request:api';
      const cause = errorData.cause || errorData.detail || 'Unknown error';
      throw new ChatSDKError(code as ErrorCode, cause);
    }

    return response;
  } catch (error: unknown) {
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      throw new ChatSDKError('offline:chat');
    }

    throw error;
  }
}

export function getLocalStorage(key: string) {
  if (typeof window !== 'undefined') {
    return JSON.parse(localStorage.getItem(key) || '[]');
  }
  return [];
}

export function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Get user ID from SSO cookie (empno)
 * SSO 인증 필수 - 쿠키 없으면 null 반환
 */
export function getUserId(): string | null {
  if (typeof window !== 'undefined') {
    // SSO 쿠키에서 empno 읽기
    const cookies = document.cookie.split(';');
    const empnoCookie = cookies.find(c => c.trim().startsWith('empno='));
    if (empnoCookie) {
      return empnoCookie.split('=')[1].trim();
    }
  }
  return null;
}

/**
 * Get user name from SSO cookie (user_name).
 * AD/LDAP 인증 시 백엔드가 set한 쿠키에서 읽음. 없으면 null.
 */
export function getUserName(): string | null {
  if (typeof window !== 'undefined') {
    const cookies = document.cookie.split(';');
    const c = cookies.find(c => c.trim().startsWith('user_name='));
    if (c) {
      try {
        return decodeURIComponent(c.split('=')[1].trim());
      } catch {
        return c.split('=')[1].trim();
      }
    }
  }
  return null;
}

export function isAdminUser(userId: string | null): boolean {
  if (!userId) return false;
  const adminUsers = (process.env.NEXT_PUBLIC_ADMIN_USERS || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
  return adminUsers.includes(userId);
}

export function isOperatorUser(userId: string | null): boolean {
  if (!userId) return false;
  const operatorUsers = (process.env.NEXT_PUBLIC_OPERATOR_USERS || 'A2304013')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
  return operatorUsers.includes(userId);
}

type ResponseMessageWithoutId = CoreToolMessage | CoreAssistantMessage;
type ResponseMessage = ResponseMessageWithoutId & { id: string };

export function getMostRecentUserMessage(messages: UIMessage[]) {
  const userMessages = messages.filter((message) => message.role === 'user');
  return userMessages.at(-1);
}

// export function getDocumentTimestampByIndex(
//   documents: Document[],
//   index: number,
// ) {
//   if (!documents) { return new Date(); }
//   if (index > documents.length) { return new Date(); }

//   return documents[index].createdAt;
// }

export function getTrailingMessageId({
  messages,
}: {
  messages: ResponseMessage[];
}): string | null {
  const trailingMessage = messages.at(-1);

  if (!trailingMessage) { return null; }

  return trailingMessage.id;
}

export function sanitizeText(text: string) {
  return text
    .replace('<has_function_call>', '')
    .replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '')
    .replace(/<tool_response>[\s\S]*?<\/tool_response>/g, '')
    .replace(/<function_calls>[\s\S]*?<\/function_calls>/g, '')
    .replace(/<function_result>[\s\S]*?<\/function_result>/g, '');
}

// export function convertToUIMessages(messages: DBMessage[]): ChatMessage[] {
//   return messages.map((message) => ({
//     id: message.id,
//role: message.role as 'user' | 'assistant' | 'system',
//     parts: message.parts as UIMessagePart<CustomUIDataTypes, ChatTools>[],
//     metadata: {
//       createdAt: formatISO(message.createdAt),
//     },
//   }));
// }

export function getTextFromMessage(message: ChatMessage | UIMessage): string {
  return message.parts
    .filter((part) => part.type === 'text')
    .map((part) => (part as { type: 'text'; text: string }).text)
    .join('');
}
