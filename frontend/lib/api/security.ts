import { getApiUrl } from "./config";

// ============================================================
// Types
// ============================================================
export type ThreatType =
  | "INJECTION"
  | "JAILBREAK"
  | "DATA_EXFIL"
  | "PRIVILEGE_ESCALATION"
  | "ABUSE"
  | "MALICIOUS_CONTENT"
  | "OTHER";

export type ActionTaken =
  | "LOGGED"
  | "WARNED"
  | "BLOCKED_REQUEST"
  | "TEMP_BLOCKED"
  | "PERM_BLOCKED";

export interface SecurityEvent {
  id: number;
  user_id: string;
  session_id: string | null;
  workspace_id: string | null;
  threat_type: ThreatType;
  severity: number;
  action_taken: ActionTaken;
  detection_layer: string;
  user_message_snippet: string | null;
  reason_snippet: string | null;
  created_at: string | null;
}

export interface SecurityEventDetail extends SecurityEvent {
  user_message: string | null;
  reason: string | null;
  matched_patterns: string | null;
  llm_raw_response: string | null;
}

export interface SecurityBlock {
  user_id: string;
  block_type: "TEMPORARY" | "PERMANENT";
  reason: string;
  threat_type: string | null;
  blocked_at: string | null;
  expires_at: string | null;
  unblocked_at: string | null;
  unblocked_by: string | null;
  temp_block_count: number;
}

export interface SecurityStats {
  summary: {
    total: number;
    warned: number;
    blocked_req: number;
    temp_blocked: number;
    perm_blocked: number;
  };
  by_threat_type: { threat_type: string; count: number }[];
  daily: { day: string; count: number }[];
  top_users: { user_id: string; count: number; max_severity: number }[];
  active_blocks: number;
}

export interface LlmUsage {
  today: {
    date: string;
    count: number;
    limit: number;
    remaining: number;
    pct: number;
  };
  recent_7days: { date: string; count: number }[];
}

// ============================================================
// API Functions
// ============================================================
const base = () => `${getApiUrl()}/api/v1/admin/security`;

export async function fetchSecurityEvents(params: {
  user_id?: string;
  threat_type?: string;
  action?: string;
  min_severity?: number;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}): Promise<{ total: number; limit: number; offset: number; events: SecurityEvent[] }> {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  });
  const res = await fetch(`${base()}/events?${q.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch events: ${res.status}`);
  return res.json();
}

export async function fetchSecurityEventDetail(id: number): Promise<SecurityEventDetail> {
  const res = await fetch(`${base()}/events/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch event: ${res.status}`);
  return res.json();
}

export async function fetchSecurityBlocks(
  includeUnblocked: boolean = false
): Promise<{ blocks: SecurityBlock[] }> {
  const q = new URLSearchParams();
  q.set("include_unblocked", String(includeUnblocked));
  const res = await fetch(`${base()}/blocks?${q.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch blocks: ${res.status}`);
  return res.json();
}

export async function unblockUser(
  userId: string,
  adminId: string,
  reason: string
): Promise<{ success: boolean; user_id: string; unblocked_by: string }> {
  const res = await fetch(`${base()}/blocks/${encodeURIComponent(userId)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ admin_id: adminId, reason }),
  });
  if (!res.ok) throw new Error(`Failed to unblock: ${res.status}`);
  return res.json();
}

export async function fetchSecurityStats(
  dateFrom: string,
  dateTo: string
): Promise<SecurityStats> {
  const q = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
  const res = await fetch(`${base()}/stats?${q.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch stats: ${res.status}`);
  return res.json();
}

export async function fetchLlmUsage(): Promise<LlmUsage> {
  const res = await fetch(`${base()}/llm-usage`);
  if (!res.ok) throw new Error(`Failed to fetch llm usage: ${res.status}`);
  return res.json();
}

export async function dryRunCheck(
  message: string
): Promise<{
  rule: { suspicion_score: number; threat_type: string | null; matched_patterns: string[] };
  llm: { threat_type?: string; severity?: number; reason?: string; error?: string } | null;
}> {
  const res = await fetch(`${base()}/dry-run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`Failed dry-run: ${res.status}`);
  return res.json();
}
