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
import { OnboardingModal } from "./onboarding-modal";

interface OnboardingContextType {
  isOpen: boolean;
  openOnboarding: () => void;
  closeOnboarding: () => void;
  hasCompletedOnboarding: boolean;
  markAsCompleted: () => void;
  resetOnboarding: () => void;
}

const OnboardingContext = createContext<OnboardingContextType | undefined>(
  undefined
);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [hasCompletedOnboarding, setHasCompletedOnboarding] = useState(true);
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    const completed = localStorage.getItem(LOCALSTORAGE_KEY);
    const version = localStorage.getItem(LOCALSTORAGE_VERSION_KEY);

    // 온보딩 비활성화 (필요 시 아래 주석 해제하여 복원)
    // const shouldShow = !completed || version !== CURRENT_ONBOARDING_VERSION;
    const shouldShow = false;

    setHasCompletedOnboarding(!shouldShow);
    setIsInitialized(true);

    if (shouldShow) {
      const timer = setTimeout(() => setIsOpen(true), 800);
      return () => clearTimeout(timer);
    }
  }, []);

  const openOnboarding = useCallback(() => {
    setIsOpen(true);
  }, []);

  const closeOnboarding = useCallback(() => {
    setIsOpen(false);
  }, []);

  const markAsCompleted = useCallback(() => {
    localStorage.setItem(LOCALSTORAGE_KEY, "true");
    localStorage.setItem(LOCALSTORAGE_VERSION_KEY, CURRENT_ONBOARDING_VERSION);
    setHasCompletedOnboarding(true);
    setIsOpen(false);
  }, []);

  const resetOnboarding = useCallback(() => {
    localStorage.removeItem(LOCALSTORAGE_KEY);
    localStorage.removeItem(LOCALSTORAGE_VERSION_KEY);
    setHasCompletedOnboarding(false);
  }, []);

  return (
    <OnboardingContext.Provider
      value={{
        isOpen,
        openOnboarding,
        closeOnboarding,
        hasCompletedOnboarding,
        markAsCompleted,
        resetOnboarding,
      }}
    >
      {children}
      {isInitialized && <OnboardingModal />}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error("useOnboarding must be used within OnboardingProvider");
  }
  return context;
}