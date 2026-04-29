"use client";

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { getApiUrl } from "@/lib/api/config";

type SystemStatus = {
  degraded: boolean;
  message: string;
  since: string | null;
};

const POLL_INTERVAL_MS = 60_000; // 60초마다 폴링

export function SystemStatusBanner() {
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const fetchStatus = async () => {
      try {
        const res = await fetch(`${getApiUrl()}/api/v1/system/status`, {
          cache: "no-store",
        });
        if (!res.ok) return;
        const data: SystemStatus = await res.json();
        if (!cancelled) setStatus(data);
      } catch {
        // 네트워크 일시 오류 — 다음 폴링에서 재시도
      } finally {
        if (!cancelled) {
          timer = setTimeout(fetchStatus, POLL_INTERVAL_MS);
        }
      }
    };

    fetchStatus();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  if (!status?.degraded) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="sticky top-0 z-50 flex items-center justify-center gap-2 bg-amber-50 px-4 py-2 text-sm text-amber-900 border-b border-amber-200 dark:bg-amber-950/40 dark:text-amber-100 dark:border-amber-900"
    >
      <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
      <span className="text-center">
        {status.message || "현재 루시드AI의 처리 작업량이 많아 지연될 수 있습니다."}
      </span>
    </div>
  );
}
