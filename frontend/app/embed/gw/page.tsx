"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { EmbedChat } from "@/components/embed-chat";
import { getApiUrl } from "@/lib/api/config";

export default function GroupwareEmbedPage() {
  const searchParams = useSearchParams();
  const gwUid = searchParams.get("empno") || "";
  const [userId, setUserId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 다우오피스 내부 user_id(숫자) → 사번 변환
  useEffect(() => {
    if (!gwUid) {
      setUserId("anonymous");
      return;
    }

    // 이미 사번 형태(문자 포함)면 변환 불필요
    if (/[a-zA-Z]/.test(gwUid)) {
      setUserId(gwUid);
      return;
    }

    // 숫자만이면 GW user_id → 사번 변환
    const baseUrl = getApiUrl();
    fetch(`${baseUrl}/api/auth/resolve-gw-user/${gwUid}`)
      .then((res) => {
        if (!res.ok) throw new Error("사용자 조회 실패");
        return res.json();
      })
      .then((data) => {
        setUserId(data.empno);
      })
      .catch((err) => {
        console.error("[GW_EMBED] User resolve failed:", err);
        setError("사용자 인증에 실패했습니다.");
      });
  }, [gwUid]);

  // embed 내 링크 클릭 시 새 탭으로 열기
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const anchor = (e.target as HTMLElement).closest("a");
      if (!anchor) return;

      const href = anchor.getAttribute("href");
      if (!href) return;

      anchor.setAttribute("target", "_blank");
      anchor.setAttribute("rel", "noopener noreferrer");
    };

    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, []);

  if (error) {
    return (
      <div className="flex h-dvh w-full items-center justify-center bg-background text-muted-foreground">
        {error}
      </div>
    );
  }

  if (!userId) {
    return (
      <div className="flex h-dvh w-full items-center justify-center bg-background text-muted-foreground">
        로딩 중...
      </div>
    );
  }

  return (
    <div className="h-dvh w-full bg-background">
      <EmbedChat userId={userId} chatMode="groupware_embed" />
    </div>
  );
}