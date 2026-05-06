import { fetchWithErrorHandlers } from "@/lib/utils";

const BASE_URL = "/api/v1/agents";

export type AgentPlatform = "native" | "miso" | "runner" | "webhook";
export type AgentStatus =
  | "draft"
  | "pending_review"
  | "pending_approval"
  | "rejected"
  | "active"
  | "maintenance"
  | "disabled"
  | "deleted";
export type AgentVisibility = "private" | "team" | "public";
export type AgentCapability = "chat" | "run" | "scheduled" | "async";

export interface AgentManifest {
  runtime: Record<string, any>;
  inputs?: Array<Record<string, any>>;
  output?: Record<string, any>;
  triggers?: Array<Record<string, any>>;
  intent_hints?: {
    system_prompt?: string;
    trigger_examples?: string[];
  };
  requires?: {
    connectors?: string[];
    permissions?: string[];
  };
}

export interface Agent {
  id: string;
  slug: string;
  name: string;
  description: string;
  icon?: string;
  tags?: string[];
  author_user_id: string;
  author_team?: string;
  platform: AgentPlatform;
  capabilities: AgentCapability[];
  visibility: AgentVisibility;
  status: AgentStatus;
  version: string;
  manifest: AgentManifest;
  install_count: number;
  is_native_seed: boolean;
  runner_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentCreatePayload {
  slug: string;
  name: string;
  description: string;
  platform: Exclude<AgentPlatform, "native">;
  capabilities: AgentCapability[];
  manifest: AgentManifest;
  visibility?: AgentVisibility;
  icon?: string;
  tags?: string[];
  author_team?: string;
  runner_id?: string;
}

export interface AgentReviewReport {
  id: string;
  agent_id: string;
  agent_version: string;
  review_round: number;
  category: "quality" | "security";
  reviewer_kind: "auto";
  reviewer_id: string;
  score: number | null;
  severity_max: "info" | "warn" | "error" | "critical";
  findings: Array<{
    severity: string;
    category: string;
    message: string;
    location?: string;
    suggestion?: string;
  }>;
  status: "passed" | "warnings" | "failed";
  created_at: string;
  completed_at?: string;
}

export const agentApi = {
  // 카탈로그
  async list(params?: {
    platform?: AgentPlatform;
    visibility?: AgentVisibility;
    status?: AgentStatus;
    is_native_seed?: boolean;
    author?: string;
    limit?: number;
    offset?: number;
  }): Promise<Agent[]> {
    const qs = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null) qs.append(k, String(v));
      });
    }
    const url = qs.toString() ? `${BASE_URL}?${qs}` : BASE_URL;
    const res = await fetchWithErrorHandlers(url);
    return res.json();
  },

  async get(slug: string): Promise<Agent> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/${slug}`);
    return res.json();
  },

  async listMyActive(): Promise<Agent[]> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/me/active`);
    return res.json();
  },

  async listReviews(slug: string): Promise<AgentReviewReport[]> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/${slug}/reviews`);
    return res.json();
  },

  async listApprovals(slug: string): Promise<Array<{
    id: string;
    agent_id: string;
    agent_version: string;
    approver_user_id: string;
    decision: "approved" | "rejected" | "request_changes";
    comment?: string;
    decided_at: string;
  }>> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/${slug}/approvals`);
    return res.json();
  },

  // 등록 / 수정 / 삭제
  async create(payload: AgentCreatePayload): Promise<Agent> {
    const res = await fetchWithErrorHandlers(BASE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return res.json();
  },

  async update(slug: string, updates: Partial<AgentCreatePayload>): Promise<Agent> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/${slug}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    return res.json();
  },

  async delete(slug: string): Promise<void> {
    await fetchWithErrorHandlers(`${BASE_URL}/${slug}`, { method: "DELETE" });
  },

  async changeStatus(slug: string, status: "active" | "maintenance" | "disabled"): Promise<Agent> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/${slug}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    return res.json();
  },

  // 설치
  async install(slug: string): Promise<{ installed: boolean; agent_id: string }> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/${slug}/install`, { method: "POST" });
    return res.json();
  },

  async uninstall(slug: string): Promise<{ uninstalled: boolean }> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/${slug}/install`, { method: "DELETE" });
    return res.json();
  },

  // 워크스페이스 부착
  async listWorkspaceAgents(workspaceId: string): Promise<Agent[]> {
    const res = await fetchWithErrorHandlers(`/api/v1/workspaces/${workspaceId}/agents`);
    return res.json();
  },

  async attachToWorkspace(workspaceId: string, slug: string): Promise<{ attached: boolean }> {
    const res = await fetchWithErrorHandlers(
      `/api/v1/workspaces/${workspaceId}/agents?slug=${encodeURIComponent(slug)}`,
      { method: "POST" },
    );
    return res.json();
  },

  async detachFromWorkspace(workspaceId: string, slug: string): Promise<{ detached: boolean }> {
    const res = await fetchWithErrorHandlers(
      `/api/v1/workspaces/${workspaceId}/agents/${encodeURIComponent(slug)}`,
      { method: "DELETE" },
    );
    return res.json();
  },

  // MISO 키 검증 + Chat/Workflow 자동 판별 (입력 시점 + 등록 시점 모두 사용)
  async probeMiso(apiKey: string): Promise<{
    valid: boolean;
    mode?: "chat" | "workflow";
    endpoint?: string;
    reason?: string;
    diagnostic?: {
      chat_status: number;
      workflow_status: number;
      chat_body?: string;
      workflow_body?: string;
    };
  }> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/miso/probe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
    return res.json();
  },

  // 승인 (operator)
  async listApprovalQueue(): Promise<Agent[]> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/admin/approval-queue`);
    return res.json();
  },

  async submitApproval(
    slug: string,
    decision: "approved" | "rejected" | "request_changes",
    comment?: string,
    reportIds?: string[],
  ): Promise<{ approval_id: string; agent_id: string; decision: string; new_status: string }> {
    const res = await fetchWithErrorHandlers(`${BASE_URL}/${slug}/approvals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, comment, report_ids: reportIds }),
    });
    return res.json();
  },
};
