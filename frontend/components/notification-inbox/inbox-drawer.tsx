"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bell,
  CalendarClock,
  Check,
  FileBarChart,
  Mail,
  Megaphone,
  Newspaper,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useInbox, type InboxItem } from "./notification-inbox-provider";

const iconMap: Record<string, LucideIcon> = {
  CalendarClock,
  Zap,
  Mail,
  Megaphone,
  Newspaper,
  ShieldCheck,
  FileBarChart,
  Sparkles,
  Bell,
};

type InboxTab = "personal" | "announcement";

interface InboxDrawerProps {
  openAnnouncement: () => void;
}

export function InboxDrawer({ openAnnouncement }: InboxDrawerProps) {
  const {
    isOpen,
    closeInbox,
    personalItems,
    announcementItems,
    unreadPersonal,
    unreadAnnouncement,
    markAsRead,
    markAllAsRead,
    dismiss,
  } = useInbox();
  const [tab, setTab] = useState<InboxTab>("personal");
  const router = useRouter();

  const items = tab === "personal" ? personalItems : announcementItems;
  const unread = tab === "personal" ? unreadPersonal : unreadAnnouncement;

  const handleClick = (item: InboxItem) => {
    markAsRead(item.id);
    if (item.openWhatsNew) {
      closeInbox();
      setTimeout(() => openAnnouncement(), 150);
      return;
    }
    if (item.link) {
      closeInbox();
      router.push(item.link);
    }
  };

  return (
    <Sheet open={isOpen} onOpenChange={(o) => (o ? null : closeInbox())}>
      <SheetContent side="right" className="w-full p-0 sm:max-w-md flex flex-col gap-0">
        <SheetHeader className="p-5 pb-3 border-b">
          <div className="flex items-center justify-between">
            <SheetTitle className="flex items-center gap-2 text-base">
              <Bell className="h-4 w-4" />
              알림함
            </SheetTitle>
            {unread > 0 && (
              <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => markAllAsRead(tab)}>
                <Check className="mr-1 h-3 w-3" />
                모두 읽음
              </Button>
            )}
          </div>
          <SheetDescription className="text-xs text-muted-foreground">
            공지, 스케줄 결과, 동기 완료 알림을 한 곳에서 확인하세요.
          </SheetDescription>
        </SheetHeader>

        <div className="flex gap-1 border-b px-3">
          <TabButton
            label="내 알림"
            count={unreadPersonal}
            active={tab === "personal"}
            onClick={() => setTab("personal")}
          />
          <TabButton
            label="공지사항"
            count={unreadAnnouncement}
            active={tab === "announcement"}
            onClick={() => setTab("announcement")}
          />
        </div>

        <ScrollArea className="flex-1">
          <div className="p-3 space-y-1.5">
            {items.length === 0 ? (
              <EmptyState tab={tab} />
            ) : (
              items.map((item) => (
                <InboxRow
                  key={item.id}
                  item={item}
                  onClick={() => handleClick(item)}
                  onDismiss={tab === "personal" ? () => dismiss(item.id) : undefined}
                />
              ))
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
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
        "flex items-center gap-1.5 border-b-2 px-3 pb-2.5 pt-2 text-sm transition-colors",
        active
          ? "border-primary font-semibold text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground",
      ].join(" ")}
    >
      <span>{label}</span>
      {count > 0 && (
        <Badge variant={active ? "default" : "secondary"} className="h-4 px-1.5 text-[10px]">
          {count}
        </Badge>
      )}
    </button>
  );
}

function InboxRow({
  item,
  onClick,
  onDismiss,
}: {
  item: InboxItem;
  onClick: () => void;
  onDismiss?: () => void;
}) {
  const Icon = iconMap[item.icon] ?? Bell;
  const unread = !item.readAt;

  return (
    <div
      className={[
        "group relative rounded-lg border p-3 transition-colors cursor-pointer",
        unread
          ? "border-primary/30 bg-primary/5 hover:bg-primary/10"
          : "border-border bg-card hover:bg-muted/40",
      ].join(" ")}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <div
          className={[
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
            unread ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground",
          ].join(" ")}
        >
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <p
              className={[
                "truncate text-sm",
                unread ? "font-semibold text-foreground" : "text-foreground/80",
              ].join(" ")}
            >
              {item.title}
            </p>
            {unread && (
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-label="unread" />
            )}
          </div>
          {item.body && (
            <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{item.body}</p>
          )}
          <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>{formatRelativeTime(item.createdAt)}</span>
            {item.workspaceName && (
              <>
                <span>·</span>
                <span className="truncate">{item.workspaceName}</span>
              </>
            )}
          </div>
        </div>
        {onDismiss && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="invisible h-6 w-6 shrink-0 text-muted-foreground hover:text-destructive group-hover:visible"
            onClick={(e) => {
              e.stopPropagation();
              onDismiss();
            }}
            aria-label="알림 제거"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}

function EmptyState({ tab }: { tab: InboxTab }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="rounded-full bg-muted p-3">
        {tab === "personal" ? (
          <Bell className="h-5 w-5 text-muted-foreground" />
        ) : (
          <Megaphone className="h-5 w-5 text-muted-foreground" />
        )}
      </div>
      <p className="text-sm font-semibold">
        {tab === "personal" ? "새 알림이 없습니다" : "공지가 없습니다"}
      </p>
      <p className="max-w-[240px] text-xs text-muted-foreground">
        {tab === "personal"
          ? "스케줄·동기 작업이 완료되면 여기로 알림이 들어옵니다."
          : "관리자 공지/업데이트가 도착하면 여기에 표시됩니다."}
      </p>
    </div>
  );
}

function formatRelativeTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diffMs = Math.max(0, now - then);
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "방금 전";
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}시간 전`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}일 전`;
  return new Date(iso).toLocaleDateString("ko-KR");
}
