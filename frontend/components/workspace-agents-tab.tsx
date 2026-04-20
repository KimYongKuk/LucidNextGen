"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BookOpen,
  CalendarClock,
  Database,
  ExternalLink,
  FileBarChart,
  Hourglass,
  Info,
  MapPin,
  MessageCircle,
  MessageSquare,
  Newspaper,
  Play,
  Plus,
  Receipt,
  Shield,
  Sparkles,
  Store,
  TrendingUp,
  X,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import type { Agent, Capability } from "@/lib/agent-store/types";
import {
  CAPABILITY_COLORS,
  CAPABILITY_LABELS,
  STATUS_COLORS,
  STATUS_LABELS,
  getPrimaryCapabilityColor,
} from "@/lib/agent-store/types";
import {
  getWorkspaceAgents,
  getWorkspaceAgentIds,
  setWorkspaceAgents,
} from "@/lib/agent-store/workspace-agents";
import { AgentPickerDialog } from "@/components/agent-store/agent-picker-dialog";

const iconMap: Record<string, LucideIcon> = {
  MapPin,
  FileBarChart,
  BookOpen,
  Receipt,
  Database,
  MessageCircle,
  Shield,
  TrendingUp,
  Sparkles,
  Newspaper,
};

const capabilityIconMap: Record<Capability, LucideIcon> = {
  chat: MessageSquare,
  run: Play,
  scheduled: CalendarClock,
  async: Hourglass,
};

interface WorkspaceAgentsTabProps {
  workspaceUuid: string;
  onCountChange?: (count: number) => void;
}

export function WorkspaceAgentsTab({ workspaceUuid, onCountChange }: WorkspaceAgentsTabProps) {
  const [attached, setAttached] = useState<Agent[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);

  useEffect(() => {
    const list = getWorkspaceAgents(workspaceUuid);
    setAttached(list);
    onCountChange?.(list.length);
  }, [workspaceUuid, onCountChange]);

  const attachedIds = useMemo(() => attached.map((a) => a.id), [attached]);

  const capabilityCounts = useMemo(() => {
    const counts: Record<Capability, number> = { chat: 0, run: 0, scheduled: 0, async: 0 };
    for (const a of attached) {
      for (const cap of a.capabilities) counts[cap] += 1;
    }
    return counts;
  }, [attached]);

  const warnings = useMemo(() => {
    const list: string[] = [];
    if (capabilityCounts.chat >= 3) {
      list.push(
        `대화형 Agent가 ${capabilityCounts.chat}개 붙어있어요. Intent 라우팅이 혼란스러울 수 있습니다.`,
      );
    }
    if (capabilityCounts.scheduled >= 1) {
      list.push(
        `스케줄 Agent가 ${capabilityCounts.scheduled}개 있어요. 정기 실행 결과가 이 Workspace로 전달됩니다.`,
      );
    }
    if (attached.length >= 8) {
      list.push(
        `활성 Agent가 ${attached.length}개로 많습니다. 10개 이하 권장 (라우팅 정확도).`,
      );
    }
    return list;
  }, [capabilityCounts, attached.length]);

  const persist = (ids: string[]) => {
    setWorkspaceAgents(workspaceUuid, ids);
    const list = getWorkspaceAgents(workspaceUuid);
    setAttached(list);
    onCountChange?.(list.length);
  };

  const handlePickerConfirm = (ids: string[]) => {
    const current = new Set(getWorkspaceAgentIds(workspaceUuid));
    const next = new Set(ids);
    const added = [...next].filter((id) => !current.has(id)).length;
    const removed = [...current].filter((id) => !next.has(id)).length;
    persist(ids);
    if (added > 0 || removed > 0) {
      toast.success(`Agent ${added > 0 ? `+${added}` : ""}${added > 0 && removed > 0 ? " / " : ""}${removed > 0 ? `-${removed}` : ""}`);
    }
  };

  const handleRemove = (id: string) => {
    const next = attachedIds.filter((x) => x !== id);
    persist(next);
    toast.success("Agent 제거됨");
  };

  return (
    <div className="space-y-4 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">활성 Agent</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            이 Workspace 안에서만 호출되는 Agent들입니다.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/agent-store" target="_blank">
              <Store className="mr-1.5 h-4 w-4" />
              Agent Store
              <ExternalLink className="ml-1 h-3 w-3" />
            </Link>
          </Button>
          <Button size="sm" onClick={() => setPickerOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Agent 추가
          </Button>
        </div>
      </div>

      {attached.length > 0 && (
        <CapabilityStrip counts={capabilityCounts} total={attached.length} />
      )}

      {warnings.length > 0 && (
        <div className="flex flex-col gap-1 rounded-md border border-amber-400/40 bg-amber-500/5 p-3">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      <div className="border rounded-md flex-1 overflow-hidden flex flex-col">
        {attached.length === 0 ? (
          <EmptyAttachedState onAdd={() => setPickerOpen(true)} />
        ) : (
          <div className="flex-1 overflow-y-auto">
            <div className="p-3 space-y-2">
              {attached.map((a) => (
                <AttachedAgentRow key={a.id} agent={a} onRemove={() => handleRemove(a.id)} />
              ))}
            </div>
          </div>
        )}
      </div>

      <AgentPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        attachedIds={attachedIds}
        onConfirm={handlePickerConfirm}
      />
    </div>
  );
}

function CapabilityStrip({
  counts,
  total,
}: {
  counts: Record<Capability, number>;
  total: number;
}) {
  const order: Capability[] = ["chat", "run", "scheduled", "async"];
  const items = order.filter((c) => counts[c] > 0);
  if (items.length === 0) return null;

  return (
    <div className="flex items-center gap-2 rounded-md border bg-muted/30 px-3 py-2 text-xs">
      <span className="text-muted-foreground">활성 {total}개:</span>
      {items.map((cap) => {
        const Icon = capabilityIconMap[cap];
        const color = CAPABILITY_COLORS[cap];
        return (
          <span
            key={cap}
            className="flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium"
            style={{ backgroundColor: `${color}15`, color, borderColor: `${color}40` }}
          >
            <Icon className="h-3 w-3" />
            {CAPABILITY_LABELS[cap]} × {counts[cap]}
          </span>
        );
      })}
    </div>
  );
}

function AttachedAgentRow({ agent, onRemove }: { agent: Agent; onRemove: () => void }) {
  const Icon = iconMap[agent.icon] ?? Sparkles;
  const iconColor = getPrimaryCapabilityColor(agent.capabilities);
  const statusColor = STATUS_COLORS[agent.status];

  return (
    <div className="group grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-md border bg-background p-3 transition-colors hover:bg-muted/40">
      <div
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
        style={{ backgroundColor: `${iconColor}20` }}
      >
        <Icon className="h-4 w-4" style={{ color: iconColor }} />
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Link
            href={`/agent-store/${agent.slug}`}
            target="_blank"
            className="truncate text-sm font-semibold hover:underline"
          >
            {agent.name}
          </Link>
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
            v{agent.version}
          </span>
          {agent.status !== "active" && (
            <Badge
              variant="outline"
              className="h-4 px-1.5 text-[10px] font-medium"
              style={{
                backgroundColor: `${statusColor}15`,
                color: statusColor,
                borderColor: `${statusColor}40`,
              }}
            >
              {STATUS_LABELS[agent.status]}
            </Badge>
          )}
        </div>
        <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{agent.description}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {agent.capabilities.map((cap) => (
            <CapabilityChip key={cap} capability={cap} />
          ))}
          <span className="ml-1 text-[10px] text-muted-foreground">· {agent.platform}</span>
        </div>
      </div>
      <Button
        variant="ghost"
        size="icon"
        className="invisible h-7 w-7 text-destructive hover:bg-destructive/10 hover:text-destructive group-hover:visible"
        onClick={onRemove}
        aria-label="Agent 제거"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

function CapabilityChip({ capability }: { capability: Capability }) {
  const color = CAPABILITY_COLORS[capability];
  return (
    <Badge
      variant="outline"
      className="h-4 px-1.5 text-[10px] font-medium"
      style={{ backgroundColor: `${color}15`, color, borderColor: `${color}40` }}
    >
      {CAPABILITY_LABELS[capability]}
    </Badge>
  );
}

function EmptyAttachedState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-10 text-center">
      <div className="rounded-full bg-muted p-3">
        <Sparkles className="h-6 w-6 text-muted-foreground" />
      </div>
      <div className="text-sm font-semibold">붙은 Agent가 없습니다</div>
      <div className="max-w-md text-xs text-muted-foreground">
        Agent Store에서 설치한 Agent를 이 Workspace에 붙이면,
        <br />
        해당 Workspace의 채팅에서만 자연어로 해당 Agent를 호출할 수 있습니다.
      </div>
      <Button size="sm" onClick={onAdd}>
        <Plus className="mr-1.5 h-4 w-4" />
        Agent 추가
      </Button>
      <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
        <Info className="h-3 w-3" />
        Private Agent도 붙일 수 있습니다 (내가 만든 것 포함)
      </p>
    </div>
  );
}
