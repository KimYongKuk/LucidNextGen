"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import {
  LOCALSTORAGE_KEY,
  LOCALSTORAGE_VERSION_KEY,
  CURRENT_ONBOARDING_VERSION,
} from "@/lib/onboarding/steps";
import {
  WHATS_NEW_ANNOUNCEMENTS,
  WHATS_NEW_STORAGE_PREFIX,
  type WhatsNewAnnouncement,
} from "@/lib/whats-new/announcements";
import { WhatsNewModal } from "./whats-new-modal";

interface WhatsNewContextType {
  isOpen: boolean;
  openWhatsNew: () => void;
  closeWhatsNew: () => void;
  unseenAnnouncements: WhatsNewAnnouncement[];
  allAnnouncements: WhatsNewAnnouncement[];
  displayAnnouncements: WhatsNewAnnouncement[];
  hasUnseenAnnouncements: boolean;
  markAllAsSeen: () => void;
}

const WhatsNewContext = createContext<WhatsNewContextType | undefined>(
  undefined
);

function isOnboardingCompleted(): boolean {
  try {
    const completed = localStorage.getItem(LOCALSTORAGE_KEY);
    const version = localStorage.getItem(LOCALSTORAGE_VERSION_KEY);
    return !!completed && version === CURRENT_ONBOARDING_VERSION;
  } catch {
    return false;
  }
}

function getUnseenAnnouncements(): WhatsNewAnnouncement[] {
  try {
    return WHATS_NEW_ANNOUNCEMENTS.filter((a) => {
      return !localStorage.getItem(`${WHATS_NEW_STORAGE_PREFIX}${a.id}`);
    });
  } catch {
    return [];
  }
}

function markAnnouncementsSeen(announcements: WhatsNewAnnouncement[]) {
  try {
    for (const a of announcements) {
      localStorage.setItem(`${WHATS_NEW_STORAGE_PREFIX}${a.id}`, "true");
    }
  } catch {
    // localStorage unavailable
  }
}

export function WhatsNewProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [unseenAnnouncements, setUnseenAnnouncements] = useState<WhatsNewAnnouncement[]>([]);
  const [showAllMode, setShowAllMode] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    if (!isOnboardingCompleted()) {
      setIsInitialized(true);
      return;
    }

    const unseen = getUnseenAnnouncements();
    setUnseenAnnouncements(unseen);
    setIsInitialized(true);

    if (unseen.length > 0) {
      const timer = setTimeout(() => {
        // Re-check onboarding at timer fire time
        if (isOnboardingCompleted()) {
          setShowAllMode(false);
          setIsOpen(true);
        }
      }, 1200);
      return () => clearTimeout(timer);
    }
  }, []);

  const openWhatsNew = useCallback(() => {
    setShowAllMode(true);
    setIsOpen(true);
  }, []);

  const closeWhatsNew = useCallback(() => {
    // Mark all unseen as seen when closing
    if (unseenAnnouncements.length > 0) {
      markAnnouncementsSeen(unseenAnnouncements);
      setUnseenAnnouncements([]);
    }
    setIsOpen(false);
    setShowAllMode(false);
  }, [unseenAnnouncements]);

  const markAllAsSeen = useCallback(() => {
    markAnnouncementsSeen(unseenAnnouncements);
    setUnseenAnnouncements([]);
  }, [unseenAnnouncements]);

  const displayAnnouncements = showAllMode
    ? WHATS_NEW_ANNOUNCEMENTS
    : unseenAnnouncements;

  return (
    <WhatsNewContext.Provider
      value={{
        isOpen,
        openWhatsNew,
        closeWhatsNew,
        unseenAnnouncements,
        allAnnouncements: WHATS_NEW_ANNOUNCEMENTS,
        displayAnnouncements,
        hasUnseenAnnouncements: unseenAnnouncements.length > 0,
        markAllAsSeen,
      }}
    >
      {children}
      {isInitialized && <WhatsNewModal />}
    </WhatsNewContext.Provider>
  );
}

export function useWhatsNew() {
  const context = useContext(WhatsNewContext);
  if (!context) {
    throw new Error("useWhatsNew must be used within WhatsNewProvider");
  }
  return context;
}
