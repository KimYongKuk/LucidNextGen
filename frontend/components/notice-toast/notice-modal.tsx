"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  ExternalLink,
  MessageSquare,
  Newspaper,
  Mail,
  FileCheck,
  Sparkles,
} from "lucide-react";
import { useNotifications } from "./notice-toast-provider";
import type {
  NoticeItem,
  MailItem,
  ApprovalItem,
  ReferencedItem,
  ApprovalData,
} from "@/lib/api/notifications";

function generateUUID() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

export function NoticeModal() {
  const {
    isOpen,
    summary,
    notices,
    mail,
    approvals,
    closeNotifications,
    dismissNotifications,
  } = useNotifications();

  const approvalItemCount =
    approvals.pending.items.length +
    approvals.received.items.length +
    approvals.referenced.items.length;
  const totalCount =
    notices.count + mail.count + approvalItemCount;
  if (totalCount === 0 && !isOpen) return null;

  const askLucid = (query: string) => {
    closeNotifications();
    const chatId = generateUUID();
    window.location.href = `/chat/${chatId}?query=${encodeURIComponent(query)}`;
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => !open && closeNotifications()}
    >
      <DialogContent className="flex max-h-[80vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
        {/* Header */}
        <DialogHeader className="flex-shrink-0 border-b bg-gradient-to-r from-slate-50 to-slate-100/80 p-4 pb-3 dark:from-slate-900 dark:to-slate-800/80">
          <DialogTitle className="text-base font-semibold">
            Today's Briefing
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            {totalCount > 0
              ? `아래 ${totalCount}건의 항목 중, 내용을 선택하여 인사이트를 나눠보세요.`
              : "새로운 알림이 없습니다"}
          </DialogDescription>
        </DialogHeader>

        {/* AI Summary */}
        <SummaryStrip summary={summary} />

        {/* Sections */}
        <div className="flex-1 overflow-y-auto">
          {/* 공지사항 */}
          <NoticeSection
            items={notices.items}
            count={notices.count}
            onAskLucid={askLucid}
          />

          {/* 메일 */}
          <MailSection
            items={mail.items}
            count={mail.count}
            onAskLucid={askLucid}
          />

          {/* 전자결재 */}
          <ApprovalSection approvals={approvals} onAskLucid={askLucid} />
        </div>

        {/* Footer */}
        <div className="flex flex-shrink-0 items-center justify-between border-t p-3">
          <button
            type="button"
            onClick={dismissNotifications}
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            오늘 다시 보지 않기
          </button>
          <Button onClick={closeNotifications} size="sm">
            확인
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ── AI 요약 스트립 ────────────────────────────────────────── */

function SummaryStrip({ summary }: { summary: string }) {
  return (
    <div className="flex flex-shrink-0 items-start gap-2 border-b bg-muted/30 px-4 py-3">
      <Sparkles className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-primary/60" />
      {summary ? (
        <p className="whitespace-pre-line text-xs leading-relaxed text-foreground/80">
          {summary}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground animate-pulse">
          요약 생성 중...
        </p>
      )}
    </div>
  );
}

/* ── 공지사항 섹션 ─────────────────────────────────────────── */

function NoticeSection({
  items,
  count,
  onAskLucid,
}: {
  items: NoticeItem[];
  count: number;
  onAskLucid: (q: string) => void;
}) {
  return (
    <div className="border-b last:border-b-0">
      <SectionHeader
        icon={<Newspaper className="h-4 w-4" />}
        title="공지사항"
        count={count}
        colorClass="bg-blue-50/80 dark:bg-blue-950/30"
      />
      {items.length === 0 ? (
        <EmptyMessage />
      ) : (
        <div>
          {items.map((notice) => (
            <div
              key={notice.post_id}
              className="group flex cursor-pointer items-start gap-2 px-4 py-2 hover:bg-muted/50"
              onClick={() =>
                onAskLucid(
                  `게시글 #${notice.post_id} '${notice.title}' 본문을 요약해줘`
                )
              }
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">
                  {notice.title}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {notice.board_name}
                  {notice.author && ` · ${notice.author}`}
                  {notice.author_dept && ` (${notice.author_dept})`}
                </p>
              </div>
              <div className="flex flex-shrink-0 items-center gap-1">
                <AskLucidButton
                  onClick={() =>
                    onAskLucid(
                      `게시글 #${notice.post_id} '${notice.title}' 본문을 요약해줘`
                    )
                  }
                />
                {notice.post_url && (
                  <a
                    href={notice.post_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100"
                    title="원문 보기"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 메일 섹션 ─────────────────────────────────────────────── */

function MailSection({
  items,
  count,
  onAskLucid,
}: {
  items: MailItem[];
  count: number;
  onAskLucid: (q: string) => void;
}) {
  return (
    <div className="border-b last:border-b-0">
      <SectionHeader
        icon={<Mail className="h-4 w-4" />}
        title="읽지 않은 메일"
        count={count}
        colorClass="bg-amber-50/80 dark:bg-amber-950/30"
      />
      {items.length === 0 ? (
        <EmptyMessage />
      ) : (
        <div>
          {items.map((m, idx) => (
            <div
              key={`mail-${idx}`}
              className="group flex cursor-pointer items-start gap-2 px-4 py-2 hover:bg-muted/50"
              onClick={() =>
                onAskLucid(`메일함 '${m.subject}' 메일 내용 확인해줘`)
              }
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">
                  {m.subject}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {m.from}
                  {m.date && ` · ${m.date}`}
                </p>
              </div>
              <div className="flex flex-shrink-0 items-center gap-1">
                <AskLucidButton
                  onClick={() =>
                    onAskLucid(`메일함 '${m.subject}' 메일 내용 확인해줘`)
                  }
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 전자결재 섹션 (서브카테고리 3개, 각 최대 5건) ─────────── */

function ApprovalSection({
  approvals,
  onAskLucid,
}: {
  approvals: ApprovalData;
  onAskLucid: (q: string) => void;
}) {
  const totalItems =
    approvals.pending.items.length +
    approvals.received.items.length +
    approvals.referenced.items.length;

  return (
    <div className="border-b last:border-b-0">
      <SectionHeader
        icon={<FileCheck className="h-4 w-4" />}
        title="전자결재"
        count={totalItems}
        colorClass="bg-emerald-50/80 dark:bg-emerald-950/30"
      />

      {/* 결재 미결 */}
      <ApprovalSubSection
        label="결재 미결"
        items={approvals.pending.items}
        onAskLucid={onAskLucid}
        dateField="drafted_at"
        queryPrefix="내 결재 대기함의"
      />

      {/* 수신문서 */}
      <ApprovalSubSection
        label="수신문서"
        items={approvals.received.items}
        onAskLucid={onAskLucid}
        dateField="drafted_at"
        queryPrefix="내 수신문서함의"
      />

      {/* 참조/열람 대기 */}
      <ApprovalSubSection
        label="참조/열람 대기"
        items={approvals.referenced.items}
        onAskLucid={onAskLucid}
        dateField="drafted_at"
        queryPrefix="내 참조함의"
      />
    </div>
  );
}

function ApprovalSubSection({
  label,
  items,
  onAskLucid,
  dateField,
  queryPrefix,
}: {
  label: string;
  items: (ApprovalItem | ReferencedItem)[];
  onAskLucid: (q: string) => void;
  dateField: "drafted_at";
  queryPrefix: string;
}) {
  const buildQuery = (a: ApprovalItem | ReferencedItem) =>
    `${queryPrefix} '${a.title}' (문서번호: ${a.doc_id}) 전자결재 문서 확인해줘`;

  return (
    <div>
      <div className="flex items-center gap-1.5 border-t border-dashed border-muted-foreground/15 px-4 pb-1 pt-2">
        <span className="text-xs font-medium text-muted-foreground">
          {label}
        </span>
        <span
          className={`text-xs font-medium ${
            items.length > 0 ? "text-primary" : "text-muted-foreground"
          }`}
        >
          {items.length}건
        </span>
      </div>
      {items.length === 0 ? (
        <p className="px-4 pb-2 text-xs text-muted-foreground">
          새로운 항목이 없습니다
        </p>
      ) : (
        items.map((a) => {
          const dateValue = (a as ApprovalItem).drafted_at;
          return (
            <div
              key={a.doc_id}
              className="group flex cursor-pointer items-start gap-2 px-4 py-2 hover:bg-muted/50"
              onClick={() => onAskLucid(buildQuery(a))}
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">
                  {a.title}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {a.form_name && `[${a.form_name}] `}
                  {a.drafter_name}
                  {dateValue && ` · ${dateValue.split("T")[0]}`}
                </p>
              </div>
              <div className="flex flex-shrink-0 items-center gap-1">
                <AskLucidButton
                  onClick={() => onAskLucid(buildQuery(a))}
                />
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

/* ── 공통 UI 컴포넌트 ───────────────────────────────────────── */

function SectionHeader({
  icon,
  title,
  count,
  colorClass,
}: {
  icon: React.ReactNode;
  title: string;
  count: number;
  colorClass: string;
}) {
  return (
    <div className={`flex items-center gap-2 px-4 py-2.5 ${colorClass}`}>
      <span className="text-muted-foreground">{icon}</span>
      <span className="text-sm font-medium">{title}</span>
      <span
        className={`rounded-full px-1.5 py-0.5 text-xs font-medium ${
          count > 0
            ? "bg-primary/10 text-primary"
            : "bg-muted text-muted-foreground"
        }`}
      >
        {count}건
      </span>
    </div>
  );
}

function EmptyMessage() {
  return (
    <p className="px-4 pb-3 text-xs text-muted-foreground">
      새로운 항목이 없습니다
    </p>
  );
}

function AskLucidButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-blue-50 hover:text-blue-600 group-hover:opacity-100 dark:hover:bg-blue-950"
      title="루시드에게 물어보기"
    >
      <MessageSquare className="h-3.5 w-3.5" />
    </button>
  );
}
