"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useWhatsNew } from "@/components/whats-new/whats-new-provider";
import { InboxDrawer } from "./inbox-drawer";

export type InboxCategory = "personal" | "announcement";

export type InboxItemType =
  | "schedule_done"
  | "async_done"
  | "sync_done"
  | "mail"
  | "approval"
  | "announcement"
  | "system";

export interface InboxItem {
  id: string;
  category: InboxCategory;
  type: InboxItemType;
  icon: string;
  title: string;
  body?: string;
  link?: string;
  openWhatsNew?: boolean;
  createdAt: string;
  readAt?: string | null;
  workspaceName?: string;
}

interface InboxContextType {
  isOpen: boolean;
  openInbox: () => void;
  closeInbox: () => void;
  items: InboxItem[];
  personalItems: InboxItem[];
  announcementItems: InboxItem[];
  unreadTotal: number;
  unreadPersonal: number;
  unreadAnnouncement: number;
  markAsRead: (id: string) => void;
  markAllAsRead: (category?: InboxCategory) => void;
  dismiss: (id: string) => void;
}

const InboxContext = createContext<InboxContextType | undefined>(undefined);

const READ_STORAGE_KEY = "lucid-inbox-read";

function loadReadIds(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(READ_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? new Set(parsed.filter((x): x is string => typeof x === "string")) : new Set();
  } catch {
    return new Set();
  }
}

function saveReadIds(ids: Set<string>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(READ_STORAGE_KEY, JSON.stringify(Array.from(ids)));
  } catch {
    // ignore
  }
}

function minutesAgo(mins: number): string {
  return new Date(Date.now() - mins * 60_000).toISOString();
}

function hoursAgo(hrs: number): string {
  return new Date(Date.now() - hrs * 3600_000).toISOString();
}

function daysAgo(days: number): string {
  return new Date(Date.now() - days * 86400_000).toISOString();
}

const MOCK_PERSONAL: InboxItem[] = [
  {
    id: "p-1",
    category: "personal",
    type: "schedule_done",
    icon: "CalendarClock",
    title: "Q-cost 주간 리포트 생성 완료",
    body: "2026-W15 리포트가 준비되었습니다. 확인하기",
    link: "/",
    createdAt: minutesAgo(8),
    readAt: null,
    workspaceName: "품질관리 보조",
  },
  {
    id: "p-2",
    category: "personal",
    type: "async_done",
    icon: "Zap",
    title: "세금계산서 발행 완료",
    body: "3건 중 3건 성공 · 홈택스 전송 완료",
    link: "/",
    createdAt: hoursAgo(2),
    readAt: null,
    workspaceName: "재무 업무",
  },
  {
    id: "p-3",
    category: "personal",
    type: "schedule_done",
    icon: "Newspaper",
    title: "뉴스레터 아카이빙 완료",
    body: "오늘 수신 뉴스레터 5건이 Wiki에 저장되었습니다.",
    link: "/",
    createdAt: hoursAgo(9),
    readAt: null,
    workspaceName: "마케팅 인사이트",
  },
  {
    id: "p-4",
    category: "personal",
    type: "sync_done",
    icon: "FileBarChart",
    title: "외화자금 분석 결과",
    body: "요청하신 달러 환율 주간 흐름 분석이 완료되었습니다.",
    link: "/",
    createdAt: daysAgo(1),
    readAt: daysAgo(1),
  },
];

export function NotificationInboxProvider({ children }: { children: ReactNode }) {
  const { allAnnouncements, hasUnseenAnnouncements, unseenAnnouncements, openWhatsNew } = useWhatsNew();
  const [isOpen, setIsOpen] = useState(false);
  const [personalItems, setPersonalItems] = useState<InboxItem[]>(MOCK_PERSONAL);
  const [readIds, setReadIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    setReadIds(loadReadIds());
  }, []);

  const announcementItems: InboxItem[] = useMemo(() => {
    const unseenIds = new Set(unseenAnnouncements.map((a) => a.id));
    return allAnnouncements.map((a) => {
      const firstStep = a.steps[0];
      const id = `ann-${a.id}`;
      return {
        id,
        category: "announcement" as const,
        type: "announcement" as const,
        icon: "Megaphone",
        title: firstStep?.titleKo ?? `공지 v${a.version}`,
        body: firstStep?.descriptionKo ?? a.version,
        openWhatsNew: true,
        createdAt: a.date ? new Date(a.date).toISOString() : new Date().toISOString(),
        readAt: unseenIds.has(a.id) ? null : new Date().toISOString(),
      };
    });
  }, [allAnnouncements, unseenAnnouncements]);

  const withReadState = useCallback(
    (list: InboxItem[]): InboxItem[] => {
      return list.map((item) =>
        readIds.has(item.id) ? { ...item, readAt: item.readAt ?? new Date().toISOString() } : item,
      );
    },
    [readIds],
  );

  const personalWithRead = useMemo(() => withReadState(personalItems), [personalItems, withReadState]);
  const announcementWithRead = useMemo(
    () => withReadState(announcementItems),
    [announcementItems, withReadState],
  );

  const items = useMemo(() => [...personalWithRead, ...announcementWithRead], [personalWithRead, announcementWithRead]);

  const unreadPersonal = useMemo(
    () => personalWithRead.filter((i) => !i.readAt).length,
    [personalWithRead],
  );
  const unreadAnnouncement = useMemo(
    () => (hasUnseenAnnouncements ? unseenAnnouncements.length : 0),
    [hasUnseenAnnouncements, unseenAnnouncements.length],
  );
  const unreadTotal = unreadPersonal + unreadAnnouncement;

  const markAsRead = useCallback((id: string) => {
    setReadIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      saveReadIds(next);
      return next;
    });
  }, []);

  const markAllAsRead = useCallback(
    (category?: InboxCategory) => {
      setReadIds((prev) => {
        const next = new Set(prev);
        const source = category === "personal"
          ? personalItems
          : category === "announcement"
            ? announcementItems
            : [...personalItems, ...announcementItems];
        for (const item of source) next.add(item.id);
        saveReadIds(next);
        return next;
      });
    },
    [personalItems, announcementItems],
  );

  const dismiss = useCallback((id: string) => {
    setPersonalItems((prev) => prev.filter((i) => i.id !== id));
    setReadIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      saveReadIds(next);
      return next;
    });
  }, []);

  const openInbox = useCallback(() => setIsOpen(true), []);
  const closeInbox = useCallback(() => setIsOpen(false), []);

  return (
    <InboxContext.Provider
      value={{
        isOpen,
        openInbox,
        closeInbox,
        items,
        personalItems: personalWithRead,
        announcementItems: announcementWithRead,
        unreadTotal,
        unreadPersonal,
        unreadAnnouncement,
        markAsRead,
        markAllAsRead,
        dismiss,
      }}
    >
      {children}
      <InboxDrawer openAnnouncement={openWhatsNew} />
    </InboxContext.Provider>
  );
}

export function useInbox() {
  const ctx = useContext(InboxContext);
  if (!ctx) throw new Error("useInbox must be used within NotificationInboxProvider");
  return ctx;
}
