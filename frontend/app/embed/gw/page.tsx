"use client";

import { useEffect, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { EmbedChat } from "@/components/embed-chat";
import { getUserId } from "@/lib/utils";

export default function GroupwareEmbedPage() {
  const searchParams = useSearchParams();
  // 우선순위: URL 파라미터 empno > SSO 쿠키 > anonymous
  const userId = useMemo(() => {
    return searchParams.get("empno") || getUserId() || "anonymous";
  }, [searchParams]);

  // embed 내 링크 클릭 시 새 탭으로 열기 (그룹웨어는 postMessage 불필요)
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const anchor = (e.target as HTMLElement).closest("a");
      if (!anchor) return;

      const href = anchor.getAttribute("href");
      if (!href) return;

      // 모든 링크를 새 탭으로 열기
      anchor.setAttribute("target", "_blank");
      anchor.setAttribute("rel", "noopener noreferrer");
    };

    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, []);

  return (
    <div className="h-dvh w-full bg-background">
      <EmbedChat userId={userId} chatMode="groupware_embed" />
    </div>
  );
}
