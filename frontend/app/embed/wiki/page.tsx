"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { EmbedChat } from "@/components/embed-chat";
import { getUserId } from "@/lib/utils";

export default function EmbedPage() {
  const searchParams = useSearchParams();
  // AES 암호화 토큰 (Outline 서버사이드에서 생성, iframe src URL 파라미터로 전달)
  // 백엔드 widget_auth.py가 복호화해서 사번으로 정규화 (email/login_id/사번 모두 지원)
  //
  // ⚠️ 마운트 시 1회만 캡처해야 함:
  // 첫 메시지 전송 시 multimodal-input의 window.history.pushState 호출이
  // URL을 `/chat/{sessionId}`로 바꿔버려 ?token=… 파라미터가 사라진다.
  // useMemo([searchParams])로 잡으면 다음 렌더에서 token이 undefined가 되어
  // 두 번째 메시지부터 X-Widget-Auth 헤더가 빠지고 401이 발생.
  const [widgetAuthToken] = useState<string | undefined>(
    () => searchParams.get("token") || undefined
  );

  // 우선순위: URL 파라미터 empno > SSO 쿠키 > anonymous
  // (token이 있어도 userId는 UI 표시용으로 유지 — 실제 인증은 widgetAuthToken으로)
  // 동일 사유로 마운트 시 1회만 캡처
  const [userId] = useState<string>(
    () => searchParams.get("empno") || getUserId() || "wiki_user"
  );

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
      <EmbedChat
        userId={userId}
        widgetAuthToken={widgetAuthToken}
        chatMode="outline_embed"
      />
    </div>
  );
}
