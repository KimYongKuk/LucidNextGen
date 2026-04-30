"use client";

import { useEffect, useState } from "react";
import { Download, PlusSquare, Share2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useIsMobile } from "@/hooks/use-mobile";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISS_KEY = "install-prompt-dismissed";
const SHOW_DELAY_MS = 3000;

function isStandaloneMode(): boolean {
  if (typeof window === "undefined") return false;
  if (window.matchMedia("(display-mode: standalone)").matches) return true;
  return (window.navigator as { standalone?: boolean }).standalone === true;
}

function isIOSDevice(): boolean {
  if (typeof window === "undefined") return false;
  const ua = window.navigator.userAgent;
  if (/iPhone|iPad|iPod/.test(ua)) return true;
  return /Macintosh/.test(ua) && "ontouchend" in document;
}

function isIOSSafari(): boolean {
  if (!isIOSDevice()) return false;
  const ua = window.navigator.userAgent;
  return /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
}

function isDesktopChromium(): boolean {
  if (typeof window === "undefined") return false;
  if (isIOSDevice()) return false;
  const ua = window.navigator.userAgent;
  // 모바일 제외
  if (/Mobi|Android/i.test(ua)) return false;
  // Chromium 계열 (Chrome, Edge, Brave, Opera, Arc 등 — Firefox·Safari 제외)
  return /Chrome|Chromium|Edg|OPR/.test(ua) && !/Firefox/.test(ua);
}

function detectBrowser(): "chrome" | "edge" | "other" {
  if (typeof window === "undefined") return "other";
  const ua = window.navigator.userAgent;
  if (/Edg/.test(ua)) return "edge";
  if (/Chrome/.test(ua)) return "chrome";
  return "other";
}

function wasDismissedThisSession(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return sessionStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

export function InstallPromptBanner() {
  const isMobile = useIsMobile();
  const [installEvent, setInstallEvent] =
    useState<BeforeInstallPromptEvent | null>(null);
  const [guideMode, setGuideMode] = useState<"ios" | "desktop" | null>(null);
  const [guideExpanded, setGuideExpanded] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // 데스크톱은 일단 비활성화 — 모바일에서만 안내
    if (!isMobile) return;
    if (isStandaloneMode()) return;
    if (wasDismissedThisSession()) return;

    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setInstallEvent(e as BeforeInstallPromptEvent);
      setGuideMode(null);
      setVisible(true);
    };
    window.addEventListener("beforeinstallprompt", handleBeforeInstall);

    const installedHandler = () => {
      setVisible(false);
      setInstallEvent(null);
    };
    window.addEventListener("appinstalled", installedHandler);

    // Fallback guide for environments where beforeinstallprompt doesn't fire:
    // - iOS Safari (no support at all)
    // - Desktop Chromium where engagement/HTTPS conditions aren't met
    let fallbackTimer: ReturnType<typeof setTimeout> | null = null;
    const showFallback = () => {
      // beforeinstallprompt가 이미 들어왔으면 fallback은 무시
      if (installEvent) return;
      if (isMobile && isIOSSafari()) {
        setGuideMode("ios");
        setVisible(true);
      } else if (!isMobile && isDesktopChromium()) {
        setGuideMode("desktop");
        setVisible(true);
      }
    };
    fallbackTimer = setTimeout(showFallback, SHOW_DELAY_MS);

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstall);
      window.removeEventListener("appinstalled", installedHandler);
      if (fallbackTimer) clearTimeout(fallbackTimer);
    };
  }, [isMobile, installEvent]);

  const handleInstall = async () => {
    if (!installEvent) return;
    try {
      await installEvent.prompt();
      const result = await installEvent.userChoice;
      if (result.outcome === "accepted") {
        setVisible(false);
        setInstallEvent(null);
      } else {
        handleDismiss();
      }
    } catch {
      handleDismiss();
    }
  };

  const handleDismiss = () => {
    try {
      sessionStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // ignore storage errors
    }
    setVisible(false);
    setGuideExpanded(false);
  };

  if (!visible) return null;
  if (!installEvent && !guideMode) return null;

  // Guide expanded (iOS or Desktop fallback)
  if (guideMode && guideExpanded) {
    if (guideMode === "ios") {
      return (
        <div className="fixed inset-x-2 bottom-2 z-50 rounded-2xl border bg-background p-4 shadow-2xl animate-in slide-in-from-bottom-4 sm:inset-x-auto sm:right-4 sm:bottom-4 sm:max-w-sm">
          <div className="mb-3 flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <Download className="h-5 w-5 text-primary" />
              <h3 className="text-sm font-semibold">홈 화면에 추가하기</h3>
            </div>
            <button
              type="button"
              onClick={handleDismiss}
              className="rounded-md p-1 text-muted-foreground hover:bg-muted"
              aria-label="닫기"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <ol className="space-y-2.5 text-xs text-foreground">
            <li className="flex items-start gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
                1
              </span>
              <span className="leading-relaxed">
                하단 메뉴바의
                <Share2 className="mx-1 inline h-3.5 w-3.5 align-text-bottom" />
                <strong>공유</strong> 버튼을 누르세요
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
                2
              </span>
              <span className="leading-relaxed">
                <PlusSquare className="mx-1 inline h-3.5 w-3.5 align-text-bottom" />
                <strong>홈 화면에 추가</strong>를 선택하세요
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
                3
              </span>
              <span className="leading-relaxed">
                우측 상단의 <strong>추가</strong>를 누르면 완료
              </span>
            </li>
          </ol>

          <p className="mt-3 text-[11px] text-muted-foreground">
            홈 화면에 추가하면 일반 앱처럼 빠르게 실행되고 알림도 받을 수 있어요.
          </p>
        </div>
      );
    }

    // Desktop fallback guide
    const browser = detectBrowser();
    const browserName = browser === "edge" ? "Edge" : "Chrome";
    return (
      <div className="fixed inset-x-2 bottom-2 z-50 rounded-2xl border bg-background p-4 shadow-2xl animate-in slide-in-from-bottom-4 sm:inset-x-auto sm:right-4 sm:bottom-4 sm:max-w-sm">
        <div className="mb-3 flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <Download className="h-5 w-5 text-primary" />
            <h3 className="text-sm font-semibold">데스크톱 앱으로 설치하기</h3>
          </div>
          <button
            type="button"
            onClick={handleDismiss}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted"
            aria-label="닫기"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <ol className="space-y-2.5 text-xs text-foreground">
          <li className="flex items-start gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
              1
            </span>
            <span className="leading-relaxed">
              주소창 우측의{" "}
              <strong>
                {browser === "edge" ? "⊕ 또는 모니터 아이콘" : "💻 모니터+화살표 아이콘"}
              </strong>
              을 클릭하세요
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
              2
            </span>
            <span className="leading-relaxed">
              아이콘이 안 보이면 우상단{" "}
              <strong>메뉴(⋯) → {browser === "edge" ? "기타 도구 → 앱 → 이 사이트를 앱으로 설치" : "캐스트, 저장 및 공유 → 페이지를 앱으로 설치"}</strong>
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
              3
            </span>
            <span className="leading-relaxed">
              <strong>설치</strong>를 누르면 완료
            </span>
          </li>
        </ol>

        <p className="mt-3 text-[11px] text-muted-foreground">
          설치하면 별도 창으로 실행되고 작업표시줄에서 바로 호출할 수 있어요.
          {browser === "other" && " (Chrome 또는 Edge에서만 가능)"}
        </p>
      </div>
    );
  }

  // Compact banner
  let title = "Lucid AI를 앱처럼 사용하세요";
  let subtitle: string;
  let buttonLabel: string;

  if (installEvent) {
    subtitle = isMobile
      ? "1초만에 홈 화면에 추가됩니다"
      : "1초만에 데스크톱에 설치됩니다";
    buttonLabel = "설치";
  } else if (guideMode === "ios") {
    subtitle = "홈 화면에 추가하면 더 빨라요";
    buttonLabel = "방법";
  } else {
    // desktop guide
    subtitle = "데스크톱 앱처럼 별도 창으로 실행";
    buttonLabel = "방법";
  }

  return (
    <div className="fixed inset-x-2 bottom-2 z-50 rounded-2xl border bg-background shadow-2xl animate-in slide-in-from-bottom-4 sm:inset-x-auto sm:right-4 sm:bottom-4 sm:max-w-md">
      <div className="flex items-center gap-3 p-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10">
          <Download className="h-5 w-5 text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold leading-tight">
            {title}
          </p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {subtitle}
          </p>
        </div>
        <Button
          size="sm"
          onClick={
            installEvent ? handleInstall : () => setGuideExpanded(true)
          }
          className="shrink-0"
        >
          {buttonLabel}
        </Button>
        <button
          type="button"
          onClick={handleDismiss}
          className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-muted"
          aria-label="닫기"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
