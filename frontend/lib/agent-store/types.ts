export type Capability = "chat" | "run" | "scheduled" | "async";
export type AgentStatus = "active" | "maintenance" | "inactive";
export type Visibility = "private" | "team" | "public";

export interface AgentParameter {
  name: string;
  type: string;
  description: string;
  required: boolean;
}

export interface ExecutionHistory {
  id: string;
  timestamp: string;
  user: string;
  status: "success" | "failed" | "running";
  duration?: string;
}

export interface Author {
  name: string;
  userId: string;
  department: string;
}

export interface Agent {
  id: string;
  slug: string;
  name: string;
  description: string;
  fullDescription: string;
  capabilities: Capability[];
  status: AgentStatus;
  visibility: Visibility;
  author: Author;
  platform: string;
  version: string;
  installCount: number;
  estimatedDurationSec?: number;
  icon: string;
  tags?: string[];
  parameters?: AgentParameter[];
  executionHistory: ExecutionHistory[];
  isInstalled: boolean;
  isMine: boolean;
}

export const CAPABILITY_LABELS: Record<Capability, string> = {
  chat: "대화형",
  run: "실행형",
  scheduled: "스케줄",
  async: "비동기",
};

export const CAPABILITY_ICONS: Record<Capability, string> = {
  chat: "MessageSquare",
  run: "Play",
  scheduled: "CalendarClock",
  async: "Hourglass",
};

export const CAPABILITY_HINTS: Record<Capability, string> = {
  chat: "자연어로 질문하면 답변",
  run: "폼 입력으로 작업 수행",
  scheduled: "주기적으로 자동 실행",
  async: "실행 제출 후 완료되면 알림",
};

export const CAPABILITY_COLORS: Record<Capability, string> = {
  chat: "#3B82F6",
  run: "#F59E0B",
  scheduled: "#8B5CF6",
  async: "#64748B",
};

export const STATUS_LABELS: Record<AgentStatus, string> = {
  active: "활성",
  maintenance: "점검중",
  inactive: "비활성",
};

export const STATUS_COLORS: Record<AgentStatus, string> = {
  active: "#10B981",
  maintenance: "#F59E0B",
  inactive: "#6B7280",
};

export const VISIBILITY_LABELS: Record<Visibility, string> = {
  private: "Private",
  team: "Team",
  public: "Public",
};

export const VISIBILITY_HINTS: Record<Visibility, string> = {
  private: "나만 사용",
  team: "우리 팀만",
  public: "전사 공개",
};

export type AgentStoreTab = "my" | "catalog" | "mine";

export const TAB_LABELS: Record<AgentStoreTab, string> = {
  my: "Active Agents",
  catalog: "Catalog",
  mine: "My Creations",
};

export function getPrimaryCapabilityColor(capabilities: Capability[]): string {
  const priority: Capability[] = ["chat", "run", "scheduled", "async"];
  for (const cap of priority) {
    if (capabilities.includes(cap)) return CAPABILITY_COLORS[cap];
  }
  return "#3B82F6";
}
