"use client";

import { memo, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, CheckCircle2, XCircle, SkipForward, Clock, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TaskCoT } from "@/lib/types";

/**
 * Planner-Executor 경로의 CoT 타임라인.
 * 각 task는 헤더(현재 상태 + 제목)만 보이고, 클릭해야 상세 로그(thinking/narration) 펼침.
 * 헤더 제목은 Haiku narration에 따라 live 업데이트되어 "무엇을 하고 있는지" 직관적 노출.
 */

const statusIcon = (status: TaskCoT["status"]) => {
  const cls = "size-3 shrink-0";
  switch (status) {
    case "completed":
      return <CheckCircle2 className={cn(cls, "text-emerald-600/70 dark:text-emerald-500/70")} />;
    case "failed":
      return <XCircle className={cn(cls, "text-red-500/70")} />;
    case "skipped":
      return <SkipForward className={cn(cls, "text-muted-foreground/50")} />;
    case "awaiting_confirm":
      return <Clock className={cn(cls, "text-amber-500/70")} />;
    case "started":
    default:
      return <Loader2 className={cn(cls, "animate-spin text-muted-foreground/60")} />;
  }
};

const statusLabel = (status: TaskCoT["status"]) => {
  switch (status) {
    case "completed": return "완료";
    case "failed": return "실패";
    case "skipped": return "건너뜀";
    case "awaiting_confirm": return "대기";
    case "started": return "진행";
  }
};

// 워커 분류용 짧은 한글 라벨 (이모지 제거)
const workerLabel = (worker: string): string => {
  const map: Record<string, string> = {
    mail: "메일",
    calendar: "캘린더",
    reservation: "회의실",
    approval: "결재",
    corp_rag: "사내문서",
    it_support: "IT지원",
    acct_support: "회계지원",
    board: "게시판",
    outline: "위키",
    nas: "NAS",
    user_files: "파일",
    web_search: "웹검색",
    url_fetch: "웹페이지",
    youtube: "YouTube",
    xlsx: "엑셀",
    ppt_generation: "PPT",
    direct: "대화",
    clarify: "확인",
  };
  return map[worker] || "작업";
};

/** 헤더 제목 — 최신 narration(진행 중) 우선, 없으면 goal */
const getDynamicTitle = (cot: TaskCoT): string => {
  // 최근 narration 찾기 (현재 진행 중인 작업 상태)
  const lastNarration = [...cot.events].reverse().find((ev) => ev.kind === "narration") as
    | { kind: "narration"; content: string }
    | undefined;

  if (cot.status === "started" && lastNarration?.content) {
    return lastNarration.content;
  }
  if (cot.status === "awaiting_confirm") {
    return `${cot.goal} (승인 대기 중)`;
  }
  // 완료/실패/건너뜀 — 원 goal 표시
  return cot.goal || "(처리 중)";
};

type TaskCardProps = {
  cot: TaskCoT;
  /** 실행 중(=스트리밍 진행 중) 전체 상태. 완료 후에는 상세 축약 */
  isDone: boolean;
};

const TaskCard = memo(({ cot, isDone }: TaskCardProps) => {
  // 기본 접힘. 사용자가 눌러야 내부 상세 공개
  const [open, setOpen] = useState(false);
  const title = getDynamicTitle(cot);

  return (
    <div className="rounded border border-border/30 bg-transparent transition-colors">
      <button
        type="button"
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left hover:bg-muted/30 rounded"
        onClick={() => setOpen((v) => !v)}
      >
        {statusIcon(cot.status)}
        <span className="text-[11px] text-muted-foreground/70 shrink-0 font-medium">
          {workerLabel(cot.worker)}
        </span>
        <span className="text-sm flex-1 truncate text-foreground/90">{title}</span>
        <span className="text-[11px] text-muted-foreground/60 whitespace-nowrap">
          {cot.elapsed_ms
            ? `${(cot.elapsed_ms / 1000).toFixed(1)}s`
            : statusLabel(cot.status)}
        </span>
        {open ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground/50" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground/50" />
        )}
      </button>

      {open && (
        <div className="px-2.5 pb-2 pt-1 border-t border-border/20 space-y-1">
          {cot.events.length === 0 && !cot.error ? (
            <div className="text-xs text-muted-foreground/50 italic">시작 중…</div>
          ) : null}
          {cot.events.map((ev, i) => {
            if (ev.kind === "narration") {
              return (
                <div key={i} className="text-xs text-muted-foreground/70 pl-0.5">
                  · {ev.content}
                </div>
              );
            }
            const content = ev.content;
            const lines = content.split("\n");
            const firstTwoLines = lines.slice(0, 2).join("\n").slice(0, 200);
            const needsEllipsis = isDone && (lines.length > 2 || content.length > 200);
            return (
              <div key={i} className="text-xs text-foreground/70 whitespace-pre-wrap break-words pl-0.5">
                {isDone ? firstTwoLines : content}
                {needsEllipsis ? <span className="opacity-40"> …</span> : null}
              </div>
            );
          })}
          {cot.error && (
            <div className="text-xs text-red-500/80 pt-1 border-t border-border/20 mt-1">
              {cot.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
TaskCard.displayName = "TaskCard";

type TaskCoTTimelineProps = {
  taskCoTs: Record<string, TaskCoT>;
  /** 스트리밍 완료 여부 */
  isDone?: boolean;
};

export const TaskCoTTimeline = memo(({ taskCoTs, isDone = false }: TaskCoTTimelineProps) => {
  const tasks = Object.values(taskCoTs || {}).sort((a, b) => {
    const aNum = parseInt((a.task_id || "").replace(/\D/g, "") || "0", 10);
    const bNum = parseInt((b.task_id || "").replace(/\D/g, "") || "0", 10);
    return aNum - bNum;
  });
  const [panelOpen, setPanelOpen] = useState(!isDone);
  const [userToggled, setUserToggled] = useState(false);
  useEffect(() => {
    if (isDone && !userToggled) {
      setPanelOpen(false);
    }
  }, [isDone, userToggled]);

  if (tasks.length === 0) return null;

  const completedCount = tasks.filter((t) => t.status === "completed").length;
  const failedCount = tasks.filter((t) => t.status === "failed").length;
  const anyActive = tasks.some((t) => t.status === "started");

  return (
    <div className="mb-2.5">
      <button
        type="button"
        className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded border border-border/30 bg-transparent hover:bg-muted/30 text-xs text-muted-foreground"
        onClick={() => { setPanelOpen((v) => !v); setUserToggled(true); }}
      >
        {anyActive ? (
          <Loader2 className="size-3 animate-spin text-muted-foreground/60" />
        ) : failedCount > 0 ? (
          <XCircle className="size-3 text-red-500/70" />
        ) : (
          <CheckCircle2 className="size-3 text-emerald-600/70 dark:text-emerald-500/70" />
        )}
        <span>
          생각하는 과정 · {completedCount}/{tasks.length}
          {failedCount > 0 ? ` · 실패 ${failedCount}` : ""}
        </span>
        <span className="flex-1" />
        {panelOpen ? (
          <ChevronDown className="size-3 text-muted-foreground/50" />
        ) : (
          <ChevronRight className="size-3 text-muted-foreground/50" />
        )}
      </button>

      {panelOpen && (
        <div className="mt-1 space-y-1">
          {tasks.map((cot) => (
            <TaskCard key={cot.task_id} cot={cot} isDone={isDone} />
          ))}
        </div>
      )}
    </div>
  );
});
TaskCoTTimeline.displayName = "TaskCoTTimeline";
