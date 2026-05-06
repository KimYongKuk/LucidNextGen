"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, ClipboardCheck, Loader2, PackagePlus, Store } from "lucide-react";
import { getUserId, isOperatorUser } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import type { Agent, AgentStoreTab, Capability } from "@/lib/agent-store/types";
import { TAB_LABELS } from "@/lib/agent-store/types";
import { agentApi } from "@/lib/api/agents";
import { adaptBackendAgent } from "@/lib/agent-store/adapter";
import { AgentCard } from "./agent-card";
import { AgentFilters, type ScopeOption, type SortKey } from "./agent-filters";
import { EmptyState } from "./empty-state";

export function AgentStoreContent() {
  const router = useRouter();

  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<AgentStoreTab>("catalog");
  const [isOperator, setIsOperator] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<string | null>(null);

  useEffect(() => {
    const uid = getUserId();
    setCurrentUserId(uid);
    setIsOperator(isOperatorUser(uid));
  }, []);

  // 카탈로그 + 내 Active 동시 fetch → adapter로 mock 형식 변환
  useEffect(() => {
    if (!currentUserId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [catalog, mine] = await Promise.all([
          agentApi.list({ limit: 500 }),         // 모든 상태 (deleted 제외, 백엔드 default)
          agentApi.listMyActive().catch(() => []),
        ]);
        if (cancelled) return;
        const mineIds = new Set(mine.map((a) => a.id));
        const adapted = catalog.map((b) =>
          adaptBackendAgent(b, {
            isInstalled: mineIds.has(b.id),
            isMine: b.author_user_id === currentUserId,
          }),
        );
        setAgents(adapted);
      } catch (e: any) {
        toast.error(`카탈로그 조회 실패: ${e?.message ?? "오류"}`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentUserId]);

  const [searchQuery, setSearchQuery] = useState("");
  const [capabilityFilter, setCapabilityFilter] = useState<Capability[]>([]);
  const [scopeFilter, setScopeFilter] = useState<ScopeOption[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("popular");
  const [deleteTarget, setDeleteTarget] = useState<Agent | null>(null);
  const [deleting, setDeleting] = useState(false);

  const hasFilters =
    searchQuery !== "" ||
    capabilityFilter.length > 0 ||
    scopeFilter.length > 0;

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
        capabilityFilter.length === 0 ||
        capabilityFilter.some((c) => a.capabilities.includes(c));

      const agentScope: ScopeOption = a.isNative ? "native" : a.visibility;
      const matchesScope =
        scopeFilter.length === 0 || scopeFilter.includes(agentScope);

      return matchesSearch && matchesCapability && matchesScope;
    });

    const sorted = [...byFilter].sort((a, b) => {
      if (sortKey === "popular") return b.installCount - a.installCount;
      if (sortKey === "name") return a.name.localeCompare(b.name, "ko");
      const aLast = a.executionHistory[0]?.timestamp ?? "";
      const bLast = b.executionHistory[0]?.timestamp ?? "";
      return bLast.localeCompare(aLast);
    });

    return sorted;
  }, [agents, activeTab, searchQuery, capabilityFilter, scopeFilter, sortKey]);

  const handleCardClick = (a: Agent) => {
    router.push(`/agent-store/${a.slug}`);
  };

  const handleToggleInstall = async (id: string) => {
    const target = agents.find((a) => a.id === id);
    if (!target) return;
    if (target.isNative) {
      toast.info(`'${target.name}'은 Native Agent로 삭제할 수 없습니다.`);
      return;
    }
    const willInstall = !target.isInstalled;
    // 낙관적 UI 갱신
    setAgents((prev) =>
      prev.map((a) =>
        a.id === id
          ? {
              ...a,
              isInstalled: willInstall,
              installCount: Math.max(0, a.installCount + (willInstall ? 1 : -1)),
            }
          : a,
      ),
    );
    try {
      if (willInstall) {
        await agentApi.install(target.slug);
        toast.success(`'${target.name}' 설치 완료`);
      } else {
        await agentApi.uninstall(target.slug);
        toast.success(`'${target.name}' 제거`);
      }
    } catch (e: any) {
      // 롤백
      setAgents((prev) =>
        prev.map((a) =>
          a.id === id
            ? {
                ...a,
                isInstalled: !willInstall,
                installCount: Math.max(0, a.installCount + (willInstall ? -1 : 1)),
              }
            : a,
        ),
      );
      toast.error(`처리 실패: ${e?.message ?? "오류"}`);
    }
  };

  const handleDeleteRequest = (a: Agent) => {
    if (a.isNative) {
      toast.info(`'${a.name}'은 Native Agent로 삭제할 수 없습니다.`);
      return;
    }
    setDeleteTarget(a);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    try {
      await agentApi.delete(deleteTarget.slug);
      toast.success(`'${deleteTarget.name}' 삭제 완료`);
      setAgents((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (e: any) {
      toast.error(`삭제 실패: ${e?.message ?? "오류"}`);
    } finally {
      setDeleting(false);
    }
  };

  const handleResetFilters = () => {
    setSearchQuery("");
    setCapabilityFilter([]);
    setScopeFilter([]);
  };

  const handleGoNew = () => {
    router.push("/agent-store/new");
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
              <div className="flex items-center gap-2 sm:self-center">
                {isOperator && (
                  <Button asChild variant="outline">
                    <Link href="/admin/agent-store/approvals">
                      <ClipboardCheck className="mr-1.5 h-4 w-4" />
                      승인 큐
                    </Link>
                  </Button>
                )}
                <Button onClick={handleGoNew}>
                  <PackagePlus className="mr-1.5 h-4 w-4" />
                  등록하기
                </Button>
              </div>
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
            scopeFilter={scopeFilter}
            onScopeFilterChange={setScopeFilter}
            sortKey={sortKey}
            onSortChange={setSortKey}
          />

          {loading ? (
            <div className="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground">
              카탈로그 불러오는 중...
            </div>
          ) : visibleAgents.length > 0 ? (
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
                    onDelete={handleDeleteRequest}
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

        <AlertDialog
          open={deleteTarget !== null}
          onOpenChange={(open) => {
            if (!open && !deleting) setDeleteTarget(null);
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>이 에이전트를 삭제하시겠습니까?</AlertDialogTitle>
              <AlertDialogDescription>
                {deleteTarget ? (
                  <>
                    <strong>'{deleteTarget.name}'</strong>이(가) 카탈로그에서 제거되며,
                    설치한 사용자들도 더 이상 사용할 수 없습니다.
                    <br />
                    이 작업은 되돌릴 수 없습니다.
                  </>
                ) : null}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={deleting}>취소</AlertDialogCancel>
              <AlertDialogAction
                disabled={deleting}
                onClick={(e) => {
                  e.preventDefault();
                  handleConfirmDelete();
                }}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {deleting ? (
                  <>
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                    삭제 중...
                  </>
                ) : (
                  "삭제"
                )}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
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
