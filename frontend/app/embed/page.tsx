"use client";

import { useEffect, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { EmbedChat } from "@/components/embed-chat";
import { getUserId } from "@/lib/utils";

export default function EmbedPage() {
  const searchParams = useSearchParams();
  // 우선순위: URL 파라미터 empno > SSO 쿠키 > anonymous
  const userId = useMemo(() => {
    return searchParams.get("empno") || getUserId() || "anonymous";
  }, [searchParams]);

  // embed 내 링크 클릭 시 부모 프레임(L&F Wiki)으로 postMessage 전송
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const anchor = (e.target as HTMLElement).closest("a");
      if (!anchor) return;

      const href = anchor.getAttribute("href");
      if (!href) return;

      // Outline 내부 경로 (/doc/xxx) 또는 같은 호스트 URL
      const isOutlineLink =
        href.startsWith("/doc/") ||
        href.startsWith("/collection/") ||
        href.includes("192.168.90.30:3003");

      if (isOutlineLink) {
        e.preventDefault();
        // 상대 경로로 변환
        const url = href.includes("://")
          ? new URL(href).pathname
          : href;
        window.parent.postMessage({ type: "lucid-navigate", url }, "*");
      } else {
        // 외부 링크는 새 탭으로
        anchor.setAttribute("target", "_blank");
        anchor.setAttribute("rel", "noopener noreferrer");
      }
    };

    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, []);

  return (
    <div className="h-dvh w-full bg-background">
      <EmbedChat userId={userId} />
    </div>
  );
}
