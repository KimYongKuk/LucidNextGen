"use client";

import { useMemo, useState, useEffect } from "react";
import {
  BookOpen,
  Check,
  Database,
  FileBarChart,
  MapPin,
  MessageCircle,
  Newspaper,
  Receipt,
  Search,
  Shield,
  Sparkles,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Agent, Capability } from "@/lib/agent-store/types";
import {
  CAPABILITY_COLORS,
  CAPABILITY_LABELS,
  getPrimaryCapabilityColor,
} from "@/lib/agent-store/types";
import { getInstalledAgents } from "@/lib/agent-store/workspace-agents";

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

interface AgentPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachedIds: string[];
  onConfirm: (nextIds: string[]) => void;
}

export function AgentPickerDialog({
  open,
  onOpenChange,
  attachedIds,
  onConfirm,
}: AgentPickerDialogProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set(attachedIds));
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (open) {
      setSelected(new Set(attachedIds));
      setQuery("");
    }
  }, [open, attachedIds]);

  const installedAgents = useMemo(() => getInstalledAgents(), []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q === "") return installedAgents;
    return installedAgents.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        (a.tags ?? []).some((t) => t.toLowerCase().includes(q)),
    );
  }, [installedAgents, query]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSave = () => {
    onConfirm(Array.from(selected));
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[640px] h-[640px] flex flex-col p-0 gap-0">
        <DialogHeader className="p-6 pb-4 border-b">
          <DialogTitle>Workspace에 Agent 붙이기</DialogTitle>
          <DialogDescription>
            내가 설치한 Agent 중 이 Workspace에서 사용할 것을 선택하세요.
          </DialogDescription>
        </DialogHeader>

        <div className="p-4 border-b">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Agent 이름 · 설명 · 태그 검색"
              className="pl-10"
            />
          </div>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-4 space-y-2">
            {installedAgents.length === 0 ? (
              <EmptyInstalledState />
            ) : filtered.length === 0 ? (
              <div className="py-12 text-center text-sm text-muted-foreground">
                검색 결과가 없습니다
              </div>
            ) : (
              filtered.map((a) => (
                <AgentPickerRow
                  key={a.id}
                  agent={a}
                  checked={selected.has(a.id)}
                  onToggle={() => toggle(a.id)}
                />
              ))
            )}
          </div>
        </ScrollArea>

        <DialogFooter className="p-4 border-t bg-muted/10">
          <div className="mr-auto text-xs text-muted-foreground">
            {selected.size}개 선택됨
          </div>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button onClick={handleSave}>저장</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AgentPickerRow({
  agent,
  checked,
  onToggle,
}: {
  agent: Agent;
  checked: boolean;
  onToggle: () => void;
}) {
  const Icon = iconMap[agent.icon] ?? Sparkles;
  const iconColor = getPrimaryCapabilityColor(agent.capabilities);

  return (
    <button
      type="button"
      onClick={onToggle}
      className={[
        "w-full flex items-start gap-3 rounded-lg border p-3 text-left transition-colors",
        checked
          ? "border-primary bg-primary/5 hover:bg-primary/10"
          : "border-border bg-card hover:bg-muted/50",
      ].join(" ")}
    >
      <div
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
        style={{ backgroundColor: `${iconColor}20` }}
      >
        <Icon className="h-4 w-4" style={{ color: iconColor }} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold">{agent.name}</span>
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
            v{agent.version}
          </span>
        </div>
        <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{agent.description}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {agent.capabilities.map((cap) => (
            <CapabilityChip key={cap} capability={cap} />
          ))}
          <span className="text-[10px] text-muted-foreground ml-1">
            · {agent.author.department}
          </span>
        </div>
      </div>
      <div
        className={[
          "shrink-0 flex h-5 w-5 items-center justify-center rounded-full border-2 transition-colors",
          checked ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/30",
        ].join(" ")}
      >
        {checked ? <Check className="h-3 w-3" /> : null}
      </div>
    </button>
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

function EmptyInstalledState() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-muted/30 py-12 text-center">
      <Sparkles className="h-7 w-7 text-muted-foreground" />
      <div className="text-sm font-semibold">설치한 Agent가 없습니다</div>
      <div className="max-w-sm text-xs text-muted-foreground">
        Agent Store에서 원하는 Agent를 먼저 설치한 뒤 Workspace에 붙일 수 있습니다.
      </div>
    </div>
  );
}
