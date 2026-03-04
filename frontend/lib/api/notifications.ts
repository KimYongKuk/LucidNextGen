import { getApiUrl } from "./config";

export interface NoticeItem {
  post_id: number;
  board_name: string;
  title: string;
  author: string;
  author_dept: string;
  posted_at: string;
  post_url: string;
}

export interface MailItem {
  subject: string;
  from: string;
  date: string;
}

export interface ApprovalItem {
  doc_id: number;
  title: string;
  form_name: string;
  drafted_at: string;
  drafter_name: string;
}

export interface ReferencedItem {
  doc_id: number;
  title: string;
  form_name: string;
  drafter_name: string;
  drafted_at: string;
}

export interface SectionData<T> {
  items: T[];
  count: number;
}

export interface ApprovalData {
  pending: SectionData<ApprovalItem>;
  received: SectionData<ApprovalItem>;
  referenced: SectionData<ReferencedItem>;
}

export interface NotificationData {
  notices: SectionData<NoticeItem>;
  mail: SectionData<MailItem>;
  approvals: ApprovalData;
}

const EMPTY_APPROVALS: ApprovalData = {
  pending: { items: [], count: 0 },
  received: { items: [], count: 0 },
  referenced: { items: [], count: 0 },
};

const EMPTY_RESPONSE: NotificationData = {
  notices: { items: [], count: 0 },
  mail: { items: [], count: 0 },
  approvals: EMPTY_APPROVALS,
};

export { EMPTY_APPROVALS };

export async function fetchTodayNotifications(
  userId: string
): Promise<NotificationData> {
  try {
    const res = await fetch(
      `${getApiUrl()}/api/v1/notifications/today?user_id=${encodeURIComponent(userId)}`
    );
    if (!res.ok) return EMPTY_RESPONSE;
    return res.json();
  } catch {
    return EMPTY_RESPONSE;
  }
}

/**
 * SSE 스트리밍으로 알림 요약 텍스트 수신
 * onToken 콜백으로 토큰 단위 전달
 */
export async function streamNotificationSummary(
  data: NotificationData,
  onToken: (token: string) => void
): Promise<void> {
  try {
    const res = await fetch(
      `${getApiUrl()}/api/v1/notifications/summary/stream`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }
    );
    if (!res.ok || !res.body) return;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (payload === "[DONE]") return;
        try {
          const parsed = JSON.parse(payload);
          if (parsed.token) onToken(parsed.token);
        } catch {
          // skip malformed
        }
      }
    }
  } catch {
    // streaming failed — summary stays empty
  }
}
