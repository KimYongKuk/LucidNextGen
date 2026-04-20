import { notFound } from "next/navigation";
import { AgentDetailContent } from "@/components/agent-store/agent-detail-content";
import { MOCK_AGENTS } from "@/lib/agent-store/mock-data";

interface PageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  const agent = MOCK_AGENTS.find((a) => a.slug === id || a.id === id);
  if (!agent) return { title: "에이전트를 찾을 수 없음 · Agent Store" };
  return {
    title: `${agent.name} · Agent Store`,
    description: agent.description,
  };
}

export default async function AgentDetailPage({ params }: PageProps) {
  const { id } = await params;
  const agent = MOCK_AGENTS.find((a) => a.slug === id || a.id === id);
  if (!agent) notFound();
  return <AgentDetailContent agent={agent} />;
}
