import { getApiUrl } from './config';

// ============================================================
// Types
// ============================================================

export interface OverviewData {
  total_messages: number;
  total_sessions: number;
  active_users: number;
  daily_trend: { date: string; messages: number; sessions: number; users: number }[];
}

export interface IntentsData {
  distribution: { name: string; intentKey: string; count: number; ratio: number }[];
}

export interface IntentDetailData {
  messages: {
    datetime: string;
    userId: string;
    question: string;
    answer: string;
    workerName: string;
    responseTimeMs: number | null;
  }[];
  intentKey: string;
}

export interface QualityData {
  failCount: number;
  failRate: number;
  failByCategory: { category: string; failRate: number; failCount: number; total: number; isHighlight: boolean }[];
  recentFailures: { datetime: string; userId: string; question: string; answer: string; category: string; workerName: string }[];
}

export interface WorkspacesData {
  activeWorkspaces: number;
  totalSessions: number;
  memoryUpdates: number;
  topWorkspaces: { workspaceId: string; name: string; user: string; messages: number; documents: number; lastActive: string }[];
}

export interface ArtifactsData {
  fileUploads: number;
  imageUploads: number;
  pdfCount: number;
  xlsxCount: number;
  pptCount: number;
  dailyTrend: { date: string; pdf: number; xlsx: number; ppt: number }[];
}

export interface PerformanceData {
  avgResponseMs: number;
  p95ResponseMs: number;
  byWorker: { worker: string; avgMs: number; p95Ms: number; count: number }[];
  dailyTrend: { date: string; avgResponse: number; p95Response: number }[];
}

export interface UserRankingData {
  totalUsers: number;
  totalMessages: number;
  ranking: {
    rank: number;
    userId: string;
    messageCount: number;
    totalTokens: number;
    sessionCount: number;
    lastActive: string;
    avgResponseMs: number;
    favoriteIntent: string;
  }[];
}

export interface TokenUsageData {
  totalInputTokens: number;
  totalOutputTokens: number;
  totalCacheReadTokens: number;
  totalCacheWriteTokens: number;
  totalCalls: number;
  byModel: { modelType: string; inputTokens: number; outputTokens: number; callCount: number }[];
  byCaller: { caller: string; modelType: string; inputTokens: number; outputTokens: number; callCount: number }[];
  dailyTrend: { date: string; sonnetTokens: number; haikuTokens: number }[];
  topUsers: { userId: string; totalTokens: number; callCount: number }[];
}

export interface UserDetailData {
  messages: {
    datetime: string;
    question: string;
    answer: string;
    intent: string;
    workerName: string;
    responseTimeMs: number | null;
  }[];
  userId: string;
}

export interface WorkspaceDetailData {
  workspaceId: string;
  tab: string;
  messages?: {
    datetime: string;
    question: string;
    answer: string;
    intent: string;
    responseTimeMs: number | null;
  }[];
  documents?: {
    fileId: string;
    fileName: string;
    fileType: string;
    chunks: number;
  }[];
}

export interface AllReportData {
  overview: OverviewData;
  intents: IntentsData;
  quality: QualityData;
  workspaces: WorkspacesData;
  artifacts: ArtifactsData;
  performance: PerformanceData;
  userRanking: UserRankingData;
  tokenUsage: TokenUsageData;
}

// ============================================================
// API client
// ============================================================

const BASE = '/api/v1/admin/report';

async function fetchReport<T>(endpoint: string, dateFrom: string, dateTo: string, extraParams?: Record<string, string>): Promise<T> {
  let url = `${getApiUrl()}${BASE}${endpoint}?date_from=${dateFrom}&date_to=${dateTo}`;
  if (extraParams) {
    for (const [k, v] of Object.entries(extraParams)) {
      url += `&${k}=${encodeURIComponent(v)}`;
    }
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Report API error: ${res.status}`);
  return res.json();
}

export const reportApi = {
  getOverview: (f: string, t: string) => fetchReport<OverviewData>('/overview', f, t),
  getIntents: (f: string, t: string) => fetchReport<IntentsData>('/intents', f, t),
  getIntentDetail: (f: string, t: string, intentKey: string) => fetchReport<IntentDetailData>('/intents/detail', f, t, { intent_key: intentKey }),
  getQuality: (f: string, t: string) => fetchReport<QualityData>('/quality', f, t),
  getWorkspaces: (f: string, t: string) => fetchReport<WorkspacesData>('/workspaces', f, t),
  getArtifacts: (f: string, t: string) => fetchReport<ArtifactsData>('/artifacts', f, t),
  getPerformance: (f: string, t: string) => fetchReport<PerformanceData>('/performance', f, t),
  getUserRanking: (f: string, t: string) => fetchReport<UserRankingData>('/users', f, t),
  getUserDetail: (f: string, t: string, userId: string) => fetchReport<UserDetailData>('/users/detail', f, t, { user_id: userId }),
  getWorkspaceDetail: (f: string, t: string, workspaceId: string, tab: string) => fetchReport<WorkspaceDetailData>('/workspaces/detail', f, t, { workspace_id: workspaceId, tab }),
  getTokenUsage: (f: string, t: string) => fetchReport<TokenUsageData>('/token-usage', f, t),
};

// ============================================================
// Email settings types & API
// ============================================================

export interface EmailRecipient {
  id: number;
  email: string;
  name: string | null;
  active: boolean;
}

export interface EmailConfig {
  enabled: boolean;
  send_day: string;
  send_hour: number;
  recipients: EmailRecipient[];
  smtpConnected?: boolean;
}

export interface EmailHistory {
  id: number;
  sentAt: string;
  dateFrom: string;
  dateTo: string;
  recipientCount: number;
  pdfFilename: string | null;
  status: 'success' | 'partial' | 'failed';
  errorMessage: string | null;
}

const emailBase = `${BASE}/email`;

async function fetchEmailApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${getApiUrl()}${emailBase}${endpoint}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`Email API error: ${res.status}`);
  return res.json();
}

export const emailApi = {
  getConfig: () => fetchEmailApi<EmailConfig>('/config'),

  updateConfig: (data: { enabled?: boolean; send_day?: string; send_hour?: number }) =>
    fetchEmailApi<{ success: boolean; message: string }>('/config', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  addRecipient: (email: string, name?: string) =>
    fetchEmailApi<{ success: boolean; message: string }>('/recipients', {
      method: 'POST',
      body: JSON.stringify({ email, name: name || null }),
    }),

  removeRecipient: (email: string) =>
    fetch(`${getApiUrl()}${emailBase}/recipients?email=${encodeURIComponent(email)}`, {
      method: 'DELETE',
    }).then(r => r.json()),

  preview: () =>
    fetchEmailApi<{ success: boolean; filename: string; downloadUrl: string }>('/preview', {
      method: 'POST',
    }),

  sendNow: () =>
    fetchEmailApi<{ success: boolean; message: string; sent_count?: number }>('/send-now', {
      method: 'POST',
    }),

  getHistory: (limit = 20) =>
    fetchEmailApi<EmailHistory[]>(`/history?limit=${limit}`),

  testSmtp: () =>
    fetchEmailApi<{ success: boolean; message: string }>('/test-smtp', {
      method: 'POST',
    }),
};

// ============================================================
// Fetch all report data
// ============================================================

export async function fetchAllReportData(dateFrom: string, dateTo: string): Promise<AllReportData> {
  const [overview, intents, quality, workspaces, artifacts, performance, userRanking, tokenUsage] = await Promise.all([
    reportApi.getOverview(dateFrom, dateTo),
    reportApi.getIntents(dateFrom, dateTo),
    reportApi.getQuality(dateFrom, dateTo),
    reportApi.getWorkspaces(dateFrom, dateTo),
    reportApi.getArtifacts(dateFrom, dateTo),
    reportApi.getPerformance(dateFrom, dateTo),
    reportApi.getUserRanking(dateFrom, dateTo),
    reportApi.getTokenUsage(dateFrom, dateTo),
  ]);
  return { overview, intents, quality, workspaces, artifacts, performance, userRanking, tokenUsage };
}
