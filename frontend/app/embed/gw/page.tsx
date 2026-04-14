"use client";

import { useEffect, useState } from "react";
import { EmbedChat } from "@/components/embed-chat";

export default function GroupwareEmbedPage() {
  // 마운트 시 1회만 URL에서 empno, sid 추출 (이후 변경 없음)
  const [userId] = useState(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get("empno") || "anonymous";
    }
    return "anonymous";
  });

  const [initialSessionId] = useState(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get("sid") || undefined;
    }
    return undefined;
  });

  // embed 내 링크 클릭 시 새 탭으로 열기 (그룹웨어는 postMessage 불필요)
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

  return (
    <div className="h-dvh w-full bg-background">
      <EmbedChat
        userId={userId}
        chatMode="groupware_embed"
        initialSessionId={initialSessionId}
        onNewChat={() => {
          // 부모 위젯에 새 대화 요청 → 세션 리셋
          if (window.parent !== window) {
            window.parent.postMessage({ type: 'lucid-new-chat' }, '*');
          }
        }}
      />
    </div>
  );
}
