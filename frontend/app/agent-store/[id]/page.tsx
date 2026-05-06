"use client";

import { useEffect, useState, use } from "react";
import { notFound } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { AgentDetailContent } from "@/components/agent-store/agent-detail-content";
import { MOCK_AGENTS } from "@/lib/agent-store/mock-data";
import type { Agent as MockAgent } from "@/lib/agent-store/types";
import { agentApi } from "@/lib/api/agents";
import { adaptBackendAgent } from "@/lib/agent-store/adapter";
import { getUserId } from "@/lib/utils";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function AgentDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const [agent, setAgent] = useState<MockAgent | null | "loading">("loading");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const currentUserId = getUserId();
      // 1. 먼저 백엔드에서 시도
      try {
        const backend = await agentApi.get(id);
        if (cancelled) return;
        // 본인 active 목록 조회 (isInstalled 판정)
        let isInstalled = false;
        try {
          const mine = await agentApi.listMyActive();
          isInstalled = mine.some((a) => a.id === backend.id);
        } catch {
          // 무시
        }
        const isMine = !!currentUserId && backend.author_user_id === currentUserId;
        setAgent(adaptBackendAgent(backend, { isInstalled, isMine }));
        return;
      } catch {
        // 404 또는 네트워크 오류 — mock fallback
      }
      // 2. mock fallback
      const mock = MOCK_AGENTS.find((a) => a.slug === id || a.id === id);
      if (cancelled) return;
      setAgent(mock ?? null);
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (agent === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        불러오는 중...
      </div>
    );
  }
  if (!agent) {
    return (
      <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
        <h1 className="text-3xl font-bold">404</h1>
        <p className="text-sm text-muted-foreground">에이전트를 찾을 수 없습니다.</p>
        <Button asChild variant="outline">
          <Link href="/agent-store">
            <ArrowLeft className="mr-1 h-4 w-4" />
            Agent Store로
          </Link>
        </Button>
      </div>
    );
  }
  return <AgentDetailContent agent={agent} />;
}
