"use client";

import { Sparkles, Search, PackagePlus, Inbox } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { AgentStoreTab } from "@/lib/agent-store/types";

interface EmptyStateProps {
  tab: AgentStoreTab;
  hasFilters: boolean;
  onResetFilters: () => void;
  onGoCatalog: () => void;
  onGoNew: () => void;
}

export function EmptyState({ tab, hasFilters, onResetFilters, onGoCatalog, onGoNew }: EmptyStateProps) {
  if (hasFilters) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/30 px-6 py-16 text-center">
        <Search className="h-8 w-8 text-muted-foreground" />
        <div className="text-sm font-semibold">검색 결과가 없습니다</div>
        <div className="text-xs text-muted-foreground">
          필터를 조정하거나 다른 검색어를 시도해보세요.
        </div>
        <Button variant="outline" size="sm" onClick={onResetFilters}>
          필터 초기화
        </Button>
      </div>
    );
  }

  if (tab === "my") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/30 px-6 py-16 text-center">
        <Inbox className="h-8 w-8 text-muted-foreground" />
        <div className="text-sm font-semibold">아직 설치한 에이전트가 없습니다</div>
        <div className="max-w-md text-xs text-muted-foreground">
          카탈로그에서 필요한 에이전트를 설치하면, 채팅 중 자연어로 해당 에이전트를 자동 호출할 수 있습니다.
        </div>
        <Button size="sm" onClick={onGoCatalog}>
          <Sparkles className="mr-1.5 h-4 w-4" />
          카탈로그 둘러보기
        </Button>
      </div>
    );
  }

  if (tab === "mine") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/30 px-6 py-16 text-center">
        <PackagePlus className="h-8 w-8 text-muted-foreground" />
        <div className="text-sm font-semibold">등록한 에이전트가 없습니다</div>
        <div className="max-w-md text-xs text-muted-foreground">
          내가 만든 자동화나 Agent를 등록하고, Private → Team → Public 순으로 공개 범위를 넓혀가세요.
        </div>
        <Button size="sm" onClick={onGoNew}>
          <PackagePlus className="mr-1.5 h-4 w-4" />
          새 에이전트 등록
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-muted/30 px-6 py-16 text-center">
      <Inbox className="h-8 w-8 text-muted-foreground" />
      <div className="text-sm font-semibold">등록된 에이전트가 없습니다</div>
    </div>
  );
}
