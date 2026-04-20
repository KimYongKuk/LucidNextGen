"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, PackagePlus, Store } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TooltipProvider } from "@/components/ui/tooltip";
import { toast } from "sonner";
import type { Agent, AgentStoreTab, Capability, Visibility } from "@/lib/agent-store/types";
import { TAB_LABELS } from "@/lib/agent-store/types";
import { MOCK_AGENTS } from "@/lib/agent-store/mock-data";
import { AgentCard } from "./agent-card";
import { AgentFilters, type SortKey } from "./agent-filters";
import { EmptyState } from "./empty-state";

export function AgentStoreContent() {
  const router = useRouter();

  const [agents, setAgents] = useState<Agent[]>(MOCK_AGENTS);
  const [activeTab, setActiveTab] = useState<AgentStoreTab>("catalog");

  const [searchQuery, setSearchQuery] = useState("");
  const [capabilityFilter, setCapabilityFilter] = useState<Capability | "all">("all");
  const [departmentFilter, setDepartmentFilter] = useState("전체");
  const [visibilityFilter, setVisibilityFilter] = useState<Visibility | "all">("all");
  const [sortKey, setSortKey] = useState<SortKey>("popular");

  const hasFilters =
    searchQuery !== "" ||
    capabilityFilter !== "all" ||
    departmentFilter !== "전체" ||
    visibilityFilter !== "all";

  const installedCount = agents.filter((a) => a.isInstalled).length;
  const mineCount = agents.filter((a) => a.isMine).length;
  const catalogCount = agents.length;

  const visibleAgents = useMemo(() => {
    const byTab = agents.filter((a) => {
      if (activeTab === "my") return a.isInstalled;
      if (activeTab === "mine") return a.isMine;
      return true;
    });

    const byFilter = byTab.filter((a) => {
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        q === "" ||
        a.name.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        (a.tags ?? []).some((t) => t.toLowerCase().includes(q));

      const matchesCapability =
        capabilityFilter === "all" || a.capabilities.includes(capabilityFilter);
      const matchesDept = departmentFilter === "전체" || a.author.department === departmentFilter;
      const matchesVis = visibilityFilter === "all" || a.visibility === visibilityFilter;

      return matchesSearch && matchesCapability && matchesDept && matchesVis;
    });

    const sorted = [...byFilter].sort((a, b) => {
      if (sortKey === "popular") return b.installCount - a.installCount;
      if (sortKey === "name") return a.name.localeCompare(b.name, "ko");
      const aLast = a.executionHistory[0]?.timestamp ?? "";
      const bLast = b.executionHistory[0]?.timestamp ?? "";
      return bLast.localeCompare(aLast);
    });

    return sorted;
  }, [agents, activeTab, searchQuery, capabilityFilter, departmentFilter, visibilityFilter, sortKey]);

  const handleCardClick = (a: Agent) => {
    router.push(`/agent-store/${a.slug}`);
  };

  const handleToggleInstall = (id: string) => {
    setAgents((prev) =>
      prev.map((a) => {
        if (a.id !== id) return a;
        const next = !a.isInstalled;
        toast.success(next ? `'${a.name}' 설치 완료` : `'${a.name}' 제거`);
        return {
          ...a,
          isInstalled: next,
          installCount: Math.max(0, a.installCount + (next ? 1 : -1)),
        };
      }),
    );
  };

  const handleResetFilters = () => {
    setSearchQuery("");
    setCapabilityFilter("all");
    setDepartmentFilter("전체");
    setVisibilityFilter("all");
  };

  const handleGoNew = () => {
    toast.info("에이전트 등록 페이지는 준비 중입니다.");
  };

  return (
    <TooltipProvider delayDuration={200}>
      <div className="min-h-screen bg-background text-foreground">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-2">
            <div>
              <Button asChild variant="ghost" size="sm">
                <Link href="/">
                  <ArrowLeft className="mr-1 h-4 w-4" />
                  채팅으로
                </Link>
              </Button>
            </div>

            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/15">
                  <Store className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold sm:text-3xl">Agent Store</h1>
                  <p className="mt-1 text-sm text-muted-foreground">
                    사내 에이전트를 탐색하고 설치해 내 채팅에 연결하세요.
                  </p>
                </div>
              </div>
              <Button onClick={handleGoNew} className="sm:self-center">
                <PackagePlus className="mr-1.5 h-4 w-4" />
                등록하기
              </Button>
            </motion.div>
          </div>

          <div className="flex gap-1 border-b">
            <TabButton
              label={TAB_LABELS.my}
              count={installedCount}
              active={activeTab === "my"}
              onClick={() => setActiveTab("my")}
            />
            <TabButton
              label={TAB_LABELS.catalog}
              count={catalogCount}
              active={activeTab === "catalog"}
              onClick={() => setActiveTab("catalog")}
            />
            <TabButton
              label={TAB_LABELS.mine}
              count={mineCount}
              active={activeTab === "mine"}
              onClick={() => setActiveTab("mine")}
            />
          </div>

          <AgentFilters
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            capabilityFilter={capabilityFilter}
            onCapabilityFilterChange={setCapabilityFilter}
            departmentFilter={departmentFilter}
            onDepartmentFilterChange={setDepartmentFilter}
            visibilityFilter={visibilityFilter}
            onVisibilityFilterChange={setVisibilityFilter}
            sortKey={sortKey}
            onSortChange={setSortKey}
          />

          {visibleAgents.length > 0 ? (
            <>
              <p className="text-xs text-muted-foreground">
                {visibleAgents.length}개의 에이전트
              </p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {visibleAgents.map((a, i) => (
                  <AgentCard
                    key={a.id}
                    agent={a}
                    index={i}
                    onClick={() => handleCardClick(a)}
                    onToggleInstall={handleToggleInstall}
                  />
                ))}
              </div>
            </>
          ) : (
            <EmptyState
              tab={activeTab}
              hasFilters={hasFilters}
              onResetFilters={handleResetFilters}
              onGoCatalog={() => setActiveTab("catalog")}
              onGoNew={handleGoNew}
            />
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}

function TabButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "flex items-center gap-2 border-b-2 px-3 pb-2.5 pt-1 text-sm transition-colors",
        active
          ? "border-primary font-semibold text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground",
      ].join(" ")}
    >
      <span>{label}</span>
      <Badge variant={active ? "default" : "secondary"} className="h-5 px-1.5 text-[11px]">
        {count}
      </Badge>
    </button>
  );
}
