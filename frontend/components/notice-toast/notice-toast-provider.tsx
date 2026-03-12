"use client";

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useState,
  useRef,
  type ReactNode,
} from "react";
import { usePathname, useSearchParams } from "next/navigation";
import {
  fetchFastNotifications,
  fetchMailNotifications,
  streamNotificationSummary,
  EMPTY_APPROVALS,
  type NoticeItem,
  type MailItem,
  type ApprovalData,
  type SectionData,
} from "@/lib/api/notifications";
import { getUserId } from "@/lib/utils";
import { NoticeModal } from "./notice-modal";


const DISMISSED_KEY_PREFIX = "lucid-ai-notifications-dismissed:";
const SUMMARY_CACHE_KEY = "lucid-ai-notification-summary";

function getCachedSummary(): string | null {
  try {
    return sessionStorage.getItem(SUMMARY_CACHE_KEY);
  } catch {
    return null;
  }
}

function cacheSummary(text: string) {
  try {
    sessionStorage.setItem(SUMMARY_CACHE_KEY, text);
  } catch {
    // sessionStorage unavailable
  }
}

function getTodayDismissedKey(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${DISMISSED_KEY_PREFIX}${yyyy}-${mm}-${dd}`;
}

function isDismissedToday(): boolean {
  try {
    return localStorage.getItem(getTodayDismissedKey()) === "true";
  } catch {
    return false;
  }
}

function dismissToday() {
  try {
    localStorage.setItem(getTodayDismissedKey(), "true");
  } catch {
    // localStorage unavailable
  }
}

function cleanupOldKeys() {
  try {
    const todayKey = getTodayDismissedKey();
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith(DISMISSED_KEY_PREFIX) && k !== todayKey) {
        localStorage.removeItem(k);
      }
    }
  } catch {
    // ignore
  }
}

const EMPTY_SECTION = { items: [], count: 0 };

interface NotificationContextType {
  isOpen: boolean;
  summary: string;
  notices: SectionData<NoticeItem>;
  mail: SectionData<MailItem>;
  approvals: ApprovalData;
  isDataReady: boolean;
  closeNotifications: () => void;
  dismissNotifications: () => void;
  openNotifications: () => void;
  hasData: boolean;
}

const NotificationContext = createContext<NotificationContextType>({
  isOpen: false,
  summary: "",
  notices: EMPTY_SECTION,
  mail: EMPTY_SECTION,
  approvals: EMPTY_APPROVALS,
  isDataReady: false,
  closeNotifications: () => {},
  dismissNotifications: () => {},
  openNotifications: () => {},
  hasData: false,
});

export function NoticeToastProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [isOpen, setIsOpen] = useState(false);
  const [summary, setSummary] = useState("");
  const [notices, setNotices] =
    useState<SectionData<NoticeItem>>(EMPTY_SECTION);
  const [mail, setMail] = useState<SectionData<MailItem>>(EMPTY_SECTION);
  const [approvals, setApprovals] = useState<ApprovalData>(EMPTY_APPROVALS);
  const [isDataReady, setIsDataReady] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const [hasData, setHasData] = useState(false);
  const summaryStreamedRef = useRef(false);

  // sessionStorage 캐시에서 요약 복원 (새로고침 시 재생성 방지)
  const restoreCachedSummary = useCallback((): boolean => {
    const cached = getCachedSummary();
    if (cached) {
      setSummary(cached);
      summaryStreamedRef.current = true;
      return true;
    }
    return false;
  }, []);

  // 요약 스트리밍 시작
  const startSummaryStream = useCallback(
    (data: { notices: SectionData<NoticeItem>; mail: SectionData<MailItem>; approvals: ApprovalData }) => {
      if (summaryStreamedRef.current) return;
      summaryStreamedRef.current = true;
      setSummary("");

      let accumulated = "";
      streamNotificationSummary(data, (token) => {
        accumulated += token;
        setSummary((prev) => prev + token);
      }).then(() => {
        if (accumulated) cacheSummary(accumulated);
      });
    },
    []
  );

  // 데이터 로드 + 모달 즉시 표시 (로딩 UI)
  useEffect(() => {
    cleanupOldKeys();

    // 메인 화면(/)에서만 자동 알림 모달 표시 (워크스페이스 제외)
    if (pathname !== "/" || searchParams.get("workspace_id")) {
      setIsInitialized(true);
      return;
    }

    const userId = getUserId();
    if (!userId) {
      setIsInitialized(true);
      return;
    }

    let cancelled = false;

    // 모달 즉시 열기 (로딩 UI 표시)
    if (!isDismissedToday()) {
      setIsOpen(true);
    }
    setIsInitialized(true);

    // 두 API 병렬 호출, 모두 완료 후 한꺼번에 표시
    Promise.all([
      fetchFastNotifications(userId),
      fetchMailNotifications(userId),
    ]).then(([fastData, mailData]) => {
      if (cancelled) return;

      setNotices(fastData.notices);
      setApprovals(fastData.approvals);
      setMail(mailData);
      setIsDataReady(true);

      const totalCount =
        fastData.notices.count +
        mailData.count +
        fastData.approvals.pending.count +
        fastData.approvals.received.count +
        fastData.approvals.referenced.count;

      if (totalCount > 0) setHasData(true);
    });

    return () => { cancelled = true; };
  }, [pathname, searchParams]);

  // 데이터 준비 완료 시 요약 스트리밍 시작
  useEffect(() => {
    if (!isDataReady || !isOpen) return;
    if (summaryStreamedRef.current) return;

    const totalCount =
      notices.count + mail.count +
      approvals.pending.count +
      approvals.received.count +
      approvals.referenced.count;
    if (totalCount === 0) return;

    if (!restoreCachedSummary()) {
      startSummaryStream({ notices, mail, approvals });
    }
  }, [isDataReady, isOpen, notices, mail, approvals, restoreCachedSummary, startSummaryStream]);

  // 그냥 닫기 — 다음 새로고침 때 다시 뜸
  const closeNotifications = useCallback(() => {
    setIsOpen(false);
  }, []);

  // 오늘 다시 보지 않기 — 하루 종일 안 뜸
  const dismissNotifications = useCallback(() => {
    dismissToday();
    setIsOpen(false);
  }, []);

  // 종 아이콘으로 다시 열기
  const openNotifications = useCallback(() => {
    setIsOpen(true);
    if (isDataReady && !summaryStreamedRef.current) {
      if (!restoreCachedSummary()) {
        startSummaryStream({ notices, mail, approvals });
      }
    }
  }, [isDataReady, notices, mail, approvals, startSummaryStream, restoreCachedSummary]);

  return (
    <NotificationContext.Provider
      value={{
        isOpen,
        summary,
        notices,
        mail,
        approvals,
        isDataReady,
        closeNotifications,
        dismissNotifications,
        openNotifications,
        hasData,
      }}
    >
      {children}
      {isInitialized && <NoticeModal />}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  return useContext(NotificationContext);
}
