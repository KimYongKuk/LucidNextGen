import { AgentStoreContent } from "@/components/agent-store/agent-store-content";

export const metadata = {
  title: "Agent Store · Lucid AI",
  description: "사내 Agent · Workflow · Knowledge를 탐색하고 내 채팅에 연결하세요.",
};

export default function AgentStorePage() {
  return <AgentStoreContent />;
}