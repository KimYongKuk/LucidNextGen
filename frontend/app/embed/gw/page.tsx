"use client";

import { useEffect, useState } from "react";
import { EmbedChat } from "@/components/embed-chat";
import { EmbedGwExamples } from "@/components/embed-gw-examples";

export default function GroupwareEmbedPage() {
  // 마운트 시 1회만 URL에서 token(암호화) 또는 empno(legacy), sid 추출
  const [widgetAuthToken] = useState(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get("token") || undefined;
    }
    return undefined;
  });

  const [userId] = useState(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get("empno") || "widget_authenticated";
    }
    return "widget_authenticated";
  });

  const [initialSessionId] = useState(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get("sid") || undefined;
    }
    return undefined;
  });

  // URL `?gosso=` → prop으로 EmbedChat/useSimpleChat에 직접 전달
  // 쿠키 경유 경로(브라우저 캐시·SameSite 정책·iframe 쿠키 쓰기 차단)를 우회하여 확실하게 body에 실음
  const [gossoCookie] = useState(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.get("gosso") || undefined;
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
        widgetAuthToken={widgetAuthToken}
        gossoCookie={gossoCookie}
        chatMode="groupware_embed"
        initialSessionId={initialSessionId}
        onNewChat={() => {
          // 부모 위젯에 새 대화 요청 → 세션 리셋
          if (window.parent !== window) {
            window.parent.postMessage({ type: 'lucid-new-chat' }, '*');
          }
        }}
        renderEmptyExamples={({ chatId, onSelect }) => (
          <EmbedGwExamples chatId={chatId} onSelect={onSelect} />
        )}
      />
    </div>
  );
}
