"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowLeft,
  BookOpen,
  CalendarClock,
  Check,
  CheckCircle2,
  Clock,
  Cpu,
  Database,
  Download,
  FileBarChart,
  Hourglass,
  Loader2,
  MapPin,
  MessageCircle,
  MessageSquare,
  Newspaper,
  Play,
  Puzzle,
  Receipt,
  Shield,
  Tag,
  Trash2,
  TrendingUp,
  User,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
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
import type { Agent, Capability, ExecutionHistory, Visibility } from "@/lib/agent-store/types";
import { agentApi } from "@/lib/api/agents";
import { workspaceApi } from "@/lib/api/workspaces";
import { getUserId, isOperatorUser } from "@/lib/utils";
import { ResubmitStatusPanel } from "./resubmit-status-panel";
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

interface AgentDetailContentProps {
  agent: Agent;
}

export function AgentDetailContent({ agent: initialAgent }: AgentDetailContentProps) {
  const router = useRouter();
  const [agent, setAgent] = useState<Agent>(initialAgent);
  const [running, setRunning] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [isOperator, setIsOperator] = useState(false);

  useEffect(() => {
    setIsOperator(isOperatorUser(getUserId()));
  }, []);

  const Icon = iconMap[agent.icon] ?? Puzzle;
  const iconColor = getPrimaryCapabilityColor(agent.capabilities);
  const isChat = agent.capabilities.includes("chat");
  const disabled = agent.status !== "active";
  const canDelete = !agent.isNative && (agent.isMine || isOperator);

  const handleToggleInstall = async () => {
    if (agent.isNative) return; // 안전망 (UI에서 이미 차단됨)
    const willInstall = !agent.isInstalled;
    setAgent((prev) => ({
      ...prev,
      isInstalled: willInstall,
      installCount: Math.max(0, prev.installCount + (willInstall ? 1 : -1)),
    }));
    try {
      if (willInstall) await agentApi.install(agent.slug);
      else await agentApi.uninstall(agent.slug);
      toast.success(willInstall ? `'${agent.name}' 설치 완료` : `'${agent.name}' 제거`);
    } catch (e: any) {
      // 롤백
      setAgent((prev) => ({
        ...prev,
        isInstalled: !willInstall,
        installCount: Math.max(0, prev.installCount + (willInstall ? -1 : 1)),
      }));
      toast.error(`처리 실패: ${e?.message ?? "오류"}`);
    }
  };

  // "이 Agent로 워크스페이스 만들기" — 빠른 워크스페이스 생성
  const handleRun = async () => {
    if (running) return;
    setRunning(true);
    try {
      // 1. Agent 매니페스트 fetch (intent_hints.system_prompt 추출)
      let systemPrompt = "";
      try {
        const backendAgent = await agentApi.get(agent.slug);
        const hints = (backendAgent.manifest as any)?.intent_hints;
        if (hints?.system_prompt) systemPrompt = hints.system_prompt;
      } catch {
        // manifest 못 가져와도 워크스페이스는 만들 수 있음
      }

      // 2. 워크스페이스 자동 생성 (이름 + Agent의 시스템 프롬프트 합성)
      const userId = getUserId() ?? "";
      const wsName = `${agent.name} Workspace`;
      const wsInstructions = systemPrompt
        ? `# ${agent.name}\n${systemPrompt}`
        : agent.description;

      const created = await workspaceApi.create({
        user_id: userId,
        name: wsName,
        description: agent.description,
        instructions: wsInstructions,
        is_public: false,
      });

      // 3. Agent를 워크스페이스에 자동 부착
      try {
        await agentApi.attachToWorkspace(created.uuid, agent.slug);
      } catch (e: any) {
        // 부착 실패해도 워크스페이스는 만들어짐. 경고만.
        console.warn(`[handleRun] attach failed: ${e?.message}`);
      }

      toast.success(`'${wsName}' 생성 완료`);
      // 4. 워크스페이스 채팅으로 이동
      router.push(`/?workspace_id=${created.uuid}`);
    } catch (e: any) {
      toast.error(`워크스페이스 생성 실패: ${e?.message ?? "오류"}`);
    } finally {
      setRunning(false);
    }
  };

  const handleDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      await agentApi.delete(agent.slug);
      toast.success(`'${agent.name}' 삭제 완료`);
      setDeleteOpen(false);
      router.push("/agent-store");
    } catch (e: any) {
      toast.error(`삭제 실패: ${e?.message ?? "오류"}`);
      setDeleting(false);
    }
  };

  const runLabel = (!agent.isInstalled && !agent.isNative)
    ? "설치 후 사용 가능"
    : "이 Agent로 워크스페이스 만들기";

  const RunIcon = isChat ? MessageSquare : Play;

  return (
    <TooltipProvider delayDuration={200}>
      <div className="min-h-screen bg-background text-foreground">
        <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
          <div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/agent-store">
                <ArrowLeft className="mr-1 h-4 w-4" />
                Agent Store
              </Link>
            </Button>
          </div>

          <motion.header
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="flex flex-col gap-5 border-b border-border pb-6"
          >
            <div className="flex items-start gap-4">
              <div className="flex h-16 w-16 shrink-0 items-center justify-center">
                <Icon className="h-10 w-10" style={{ color: iconColor }} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <VisibilityBadge visibility={agent.visibility} />
                  <StatusChip status={agent.status} />
                  <span className="font-mono text-xs text-muted-foreground">v{agent.version}</span>
                </div>
                <h1 className="text-2xl font-bold text-balance sm:text-3xl">{agent.name}</h1>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground sm:text-base">
                  {agent.description}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {agent.capabilities.map((cap) => (
                <CapabilityPill key={cap} capability={cap} />
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <User className="h-4 w-4" />
                {agent.author.department} · {agent.author.name}
              </span>
              <span className="flex items-center gap-1.5">
                <Cpu className="h-4 w-4" />
                {agent.platform}
              </span>
              <span className="flex items-center gap-1.5">
                <Download className="h-4 w-4" />
                {agent.installCount.toLocaleString()}명 사용
              </span>
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              {agent.isNative ? (
                // Native Agent — 자동 활성, 토글 불가
                <div className="flex items-center justify-center gap-1.5 rounded-md border border-dashed border-emerald-300 bg-emerald-50/50 px-4 py-2 text-sm text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300 sm:w-44">
                  <Check className="h-4 w-4" />
                  기본 탑재
                </div>
              ) : (
                <Button
                  type="button"
                  size="lg"
                  variant={agent.isInstalled ? "outline" : "default"}
                  onClick={handleToggleInstall}
                  disabled={disabled && !agent.isInstalled}
                  className="sm:w-44"
                >
                  {agent.isInstalled ? (
                    <>
                      <Check className="mr-1.5 h-4 w-4" />
                      설치됨 (제거)
                    </>
                  ) : (
                    <>
                      <Download className="mr-1.5 h-4 w-4" />
                      설치
                    </>
                  )}
                </Button>
              )}
              <Button
                type="button"
                size="lg"
                className="flex-1"
                disabled={running || disabled || (!agent.isNative && !agent.isInstalled)}
                onClick={handleRun}
                style={{
                  backgroundColor: disabled || (!agent.isNative && !agent.isInstalled) ? undefined : iconColor,
                }}
              >
                {running ? (
                  <>
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                    워크스페이스 생성 중...
                  </>
                ) : (
                  <>
                    <RunIcon className="mr-1.5 h-4 w-4" />
                    {runLabel}
                  </>
                )}
              </Button>
              {canDelete && (
                <Button
                  type="button"
                  size="lg"
                  variant="outline"
                  onClick={() => setDeleteOpen(true)}
                  className="border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive sm:w-32"
                >
                  <Trash2 className="mr-1.5 h-4 w-4" />
                  삭제
                </Button>
              )}
            </div>
          </motion.header>

          <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>이 에이전트를 삭제하시겠습니까?</AlertDialogTitle>
                <AlertDialogDescription>
                  <strong>'{agent.name}'</strong>이(가) 카탈로그에서 제거되며,
                  설치한 사용자들도 더 이상 사용할 수 없습니다.
                  <br />
                  이 작업은 되돌릴 수 없습니다.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={deleting}>취소</AlertDialogCancel>
                <AlertDialogAction
                  disabled={deleting}
                  onClick={(e) => {
                    e.preventDefault();
                    handleDelete();
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

          {/* 진행 중/반려 상태 패널 (작성자에게 수정 후 재제출 버튼 노출) */}
          {!agent.isNative && (
            <ResubmitStatusPanel
              slug={agent.slug}
              isAuthor={agent.isMine}
            />
          )}

          <section>
            <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              <BookOpen className="h-4 w-4" />
              README
            </h2>
            <article className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h2: ({ children }) => (
                    <h2 className="mb-3 mt-6 text-xl font-bold text-foreground first:mt-0">
                      {children}
                    </h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="mb-2 mt-4 text-base font-semibold text-foreground">{children}</h3>
                  ),
                  p: ({ children }) => (
                    <p className="mb-3 text-sm leading-relaxed text-foreground/90">{children}</p>
                  ),
                  ul: ({ children }) => (
                    <ul className="mb-3 list-inside list-disc space-y-1 text-sm text-foreground/90">
                      {children}
                    </ul>
                  ),
                  ol: ({ children }) => (
                    <ol className="mb-3 list-inside list-decimal space-y-1 text-sm text-foreground/90">
                      {children}
                    </ol>
                  ),
                  li: ({ children }) => <li>{children}</li>,
                  blockquote: ({ children }) => (
                    <blockquote className="my-3 border-l-4 border-primary/50 bg-muted/30 py-2 pl-4 text-sm italic text-muted-foreground">
                      {children}
                    </blockquote>
                  ),
                  code: ({ children }) => (
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                      {children}
                    </code>
                  ),
                  hr: () => <hr className="my-6 border-border" />,
                }}
              >
                {agent.fullDescription}
              </ReactMarkdown>
            </article>
          </section>

          {agent.tags && agent.tags.length > 0 ? (
            <section>
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                <Tag className="h-4 w-4" />
                태그
              </h2>
              <div className="flex flex-wrap gap-1.5">
                {agent.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-xs font-normal">
                    #{tag}
                  </Badge>
                ))}
              </div>
            </section>
          ) : null}

          {agent.parameters && agent.parameters.length > 0 ? (
            <section>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                입력 파라미터
              </h2>
              <div className="space-y-2">
                {agent.parameters.map((p) => (
                  <div
                    key={p.name}
                    className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 p-3"
                  >
                    <code className="rounded bg-primary/15 px-2 py-0.5 font-mono text-xs text-primary">
                      {p.name}
                    </code>
                    <div className="flex-1">
                      <p className="text-sm text-foreground">{p.description}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        타입: {p.type} {p.required ? "· 필수" : ""}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <section className="rounded-lg border border-border bg-muted/20 p-4">
            <h2 className="mb-2 text-sm font-semibold text-foreground">작성자 정보</h2>
            <p className="text-sm text-muted-foreground">
              <strong className="font-medium text-foreground">{agent.author.name}</strong> · {agent.author.department} ({agent.author.userId})
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              문의 및 개선 요청은 작성자에게 직접 연락해주세요.
            </p>
          </section>
        </div>
      </div>
    </TooltipProvider>
  );
}

function CapabilityPill({ capability }: { capability: Capability }) {
  const Icon = capabilityIconMap[capability];
  const color = CAPABILITY_COLORS[capability];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium"
          style={{
            backgroundColor: `${color}15`,
            color,
            borderColor: `${color}40`,
          }}
        >
          <Icon className="h-3.5 w-3.5" />
          {CAPABILITY_LABELS[capability]}
        </span>
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
    <Badge
      variant="outline"
      className={`text-xs font-medium ${cls[visibility]}`}
      title={VISIBILITY_HINTS[visibility]}
    >
      {VISIBILITY_LABELS[visibility]}
    </Badge>
  );
}

function StatusChip({ status }: { status: Agent["status"] }) {
  return (
    <span className="flex items-center gap-1.5 text-xs">
      <span
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: STATUS_COLORS[status] }}
      />
      <span style={{ color: STATUS_COLORS[status] }}>{STATUS_LABELS[status]}</span>
    </span>
  );
}

function HistoryItem({ history }: { history: ExecutionHistory }) {
  const cfg = {
    success: { Icon: CheckCircle2, color: "#10B981" },
    failed: { Icon: XCircle, color: "#EF4444" },
    running: { Icon: Loader2, color: "#3B82F6" },
  } as const;
  const { Icon, color } = cfg[history.status];

  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/20 px-4 py-3">
      <Icon
        className={`h-4 w-4 ${history.status === "running" ? "animate-spin" : ""}`}
        style={{ color }}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-sm">
          <User className="h-3 w-3 text-muted-foreground" />
          <span className="truncate">{history.user}</span>
        </div>
      </div>
      <div className="text-right">
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          {history.timestamp}
        </div>
        {history.duration ? (
          <p className="mt-0.5 text-xs text-muted-foreground">{history.duration}</p>
        ) : null}
      </div>
    </div>
  );
}
