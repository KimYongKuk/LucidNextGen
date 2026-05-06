"use client";

import { motion } from "framer-motion";
import {
  MapPin,
  FileBarChart,
  BookOpen,
  Receipt,
  Database,
  MessageCircle,
  Shield,
  TrendingUp,
  Puzzle,
  Newspaper,
  Download,
  Check,
  MessageSquare,
  Play,
  CalendarClock,
  Hourglass,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Agent, AgentStatus, Capability, Visibility } from "@/lib/agent-store/types";
import {
  CAPABILITY_COLORS,
  CAPABILITY_HINTS,
  CAPABILITY_LABELS,
  STATUS_COLORS,
  STATUS_LABELS,
  VISIBILITY_HINTS,
  VISIBILITY_LABELS,
  getPrimaryCapabilityColor,
} from "@/lib/agent-store/types";

const iconMap: Record<string, LucideIcon> = {
  MapPin,
  FileBarChart,
  BookOpen,
  Receipt,
  Database,
  MessageCircle,
  Shield,
  TrendingUp,
  Sparkles: Puzzle,
  Newspaper,
};

const capabilityIconMap: Record<Capability, LucideIcon> = {
  chat: MessageSquare,
  run: Play,
  scheduled: CalendarClock,
  async: Hourglass,
};

interface AgentCardProps {
  agent: Agent;
  onClick: () => void;
  onToggleInstall: (id: string) => void;
  onDelete?: (agent: Agent) => void;
  index: number;
}

export function AgentCard({ agent, onClick, onToggleInstall, onDelete, index }: AgentCardProps) {
  const Icon = iconMap[agent.icon] ?? Puzzle;
  const iconColor = getPrimaryCapabilityColor(agent.capabilities);
  const disabled = agent.status !== "active";
  const canDelete = !!onDelete && agent.isMine && !agent.isNative;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.04 }}
    >
      <Card
        className="group flex h-full cursor-pointer flex-col border-border bg-card transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-primary/10"
        onClick={onClick}
      >
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="flex h-10 w-10 items-center justify-center">
              <Icon className="h-6 w-6" style={{ color: iconColor }} />
            </div>
            <VisibilityBadge visibility={agent.visibility} />
          </div>
          <h3 className="mt-3 line-clamp-2 text-base font-semibold text-foreground transition-colors group-hover:text-primary">
            {agent.name}
          </h3>
        </CardHeader>

        <CardContent className="flex flex-1 flex-col pt-0">
          <p className="line-clamp-2 text-sm leading-relaxed text-muted-foreground">
            {agent.description}
          </p>

          <div className="mt-3 flex flex-wrap gap-1.5">
            {agent.capabilities.map((cap) => (
              <CapabilityBadge key={cap} capability={cap} />
            ))}
          </div>

          <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="truncate">{agent.author.department}</span>
            <span className="text-border">·</span>
            <span className="truncate">{agent.author.name}</span>
            <span className="ml-auto shrink-0 font-mono text-[11px]">v{agent.version}</span>
          </div>

          <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
            <StatusIndicator status={agent.status} />
            <span>·</span>
            <span>
              <Download className="mr-1 inline h-3 w-3" />
              {agent.installCount.toLocaleString()}
            </span>
          </div>

          <div className="mt-4 flex-1" />

          <div className="mt-3 flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant={agent.isInstalled ? "outline" : "default"}
              className="flex-1"
              disabled={disabled && !agent.isInstalled}
              onClick={(e) => {
                e.stopPropagation();
                onToggleInstall(agent.id);
              }}
            >
              {agent.isInstalled ? (
                <>
                  <Check className="mr-1.5 h-4 w-4" />
                  설치됨
                </>
              ) : (
                <>
                  <Download className="mr-1.5 h-4 w-4" />
                  설치
                </>
              )}
            </Button>
            {canDelete && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    aria-label="에이전트 삭제"
                    className="shrink-0 border-destructive/40 px-2 text-destructive hover:bg-destructive/10 hover:text-destructive"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete!(agent);
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>삭제</TooltipContent>
              </Tooltip>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function CapabilityBadge({ capability }: { capability: Capability }) {
  const Icon = capabilityIconMap[capability];
  const color = CAPABILITY_COLORS[capability];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className="gap-1 px-1.5 py-0.5 text-[11px] font-medium"
          style={{
            backgroundColor: `${color}15`,
            color,
            borderColor: `${color}40`,
          }}
        >
          <Icon className="h-3 w-3" />
          {CAPABILITY_LABELS[capability]}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{CAPABILITY_HINTS[capability]}</TooltipContent>
    </Tooltip>
  );
}

function VisibilityBadge({ visibility }: { visibility: Visibility }) {
  const cls: Record<Visibility, string> = {
    private: "border-zinc-400/40 bg-zinc-500/10 text-zinc-500 dark:text-zinc-400",
    team: "border-violet-400/40 bg-violet-500/10 text-violet-600 dark:text-violet-400",
    public: "border-emerald-400/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  };
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className={`px-2 py-0.5 text-[11px] font-medium ${cls[visibility]}`}>
          {VISIBILITY_LABELS[visibility]}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{VISIBILITY_HINTS[visibility]}</TooltipContent>
    </Tooltip>
  );
}

function StatusIndicator({ status }: { status: AgentStatus }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: STATUS_COLORS[status] }} />
      <span style={{ color: STATUS_COLORS[status] }}>{STATUS_LABELS[status]}</span>
    </span>
  );
}
