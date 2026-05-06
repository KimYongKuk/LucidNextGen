/**
 * 백엔드 Agent 응답 → Frontend mock Agent 타입 어댑터.
 *
 * AgentDetailContent / AgentCard 등 기존 컴포넌트가 mock Agent 타입을 받으므로
 * 백엔드 응답을 형식 변환해서 전달.
 *
 * Phase 2에 mock 의존 컴포넌트를 백엔드 native 타입으로 리팩토링하면 이 어댑터 제거 가능.
 */
import type { Agent as MockAgent, AgentStatus } from "@/lib/agent-store/types";
import type { Agent as BackendAgent } from "@/lib/api/agents";

interface AdapterOptions {
  isInstalled?: boolean;
  isMine?: boolean;
}

export function adaptBackendAgent(
  b: BackendAgent,
  opts: AdapterOptions = {},
): MockAgent {
  // status 매핑: 백엔드 8상태 → mock 3상태
  const mockStatus: AgentStatus =
    b.status === "active"
      ? "active"
      : b.status === "maintenance" ||
          b.status === "pending_review" ||
          b.status === "pending_approval"
        ? "maintenance"
        : "inactive";

  // 백엔드 응답에 author_name/author_display가 채워져 있을 수 있음
  // (agent_service._serialize에서 user_directory lookup으로 자동 추가)
  const authorAny = b as any;
  const authorDisplayName =
    authorAny.author_name && authorAny.author_name !== b.author_user_id
      ? authorAny.author_name
      : b.author_user_id;

  return {
    id: b.id,
    slug: b.slug,
    name: b.name,
    description: b.description,
    fullDescription: b.description,
    capabilities: b.capabilities,
    status: mockStatus,
    visibility: b.visibility,
    author: {
      name: authorDisplayName,
      userId: b.author_user_id,
      department: authorAny.author_team ?? "",
    },
    platform: b.platform,
    version: b.version,
    installCount: b.install_count ?? 0,
    icon: b.icon ?? "🤖",
    tags: b.tags,
    parameters: [],
    executionHistory: [],
    isInstalled: b.is_native_seed ? true : (opts.isInstalled ?? false), // Native는 항상 활성
    isMine: opts.isMine ?? false,
    isNative: b.is_native_seed === true,
  };
}
