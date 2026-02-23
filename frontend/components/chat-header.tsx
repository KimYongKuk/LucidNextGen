"use client";

import { useRouter } from "next/navigation";
import { memo } from "react";
import { useWindowSize } from "usehooks-ts";
import { useTheme } from "next-themes";
import { SidebarToggle } from "@/components/sidebar-toggle";
import { Button } from "@/components/ui/button";
import { PlusIcon } from "./icons";
import { useSidebar } from "./ui/sidebar";
import { Folder, HelpCircle, Moon, Sun, Sparkles, Shield, X } from "lucide-react";
import Link from "next/link";
import { getUserId, isAdminUser } from "@/lib/utils";
import { useOnboarding } from "@/components/onboarding/onboarding-provider";
import { useWhatsNew } from "@/components/whats-new/whats-new-provider";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import type { Workspace } from "@/lib/api/workspaces";

function PureChatHeader({
  chatId,
  isReadonly,
  workspace,
}: {
  chatId: string;
  isReadonly: boolean;
  workspace?: Workspace | null;
}) {
  const router = useRouter();
  const { open } = useSidebar();
  const { theme, setTheme } = useTheme();
  const { openOnboarding } = useOnboarding();
  const { openWhatsNew, hasUnseenAnnouncements } = useWhatsNew();
  const isAdmin = isAdminUser(getUserId());

  const { width: windowWidth } = useWindowSize();

  return (
    <header className="sticky top-0 flex items-center gap-2 bg-background px-2 py-1.5 md:px-2">
      <SidebarToggle />

      {(!open || windowWidth < 768) && (
        <Button
          className="order-2 ml-auto h-8 px-2 md:order-1 md:ml-0 md:h-fit md:px-2"
          onClick={() => {
            if (workspace) {
              router.push(`/?workspace_id=${workspace.uuid}`);
            } else {
              router.push("/");
            }
            router.refresh();
          }}
          variant="outline"
        >
          <PlusIcon />
          <span className="md:sr-only">New Chat</span>
        </Button>
      )}

      {workspace && (
        <div className="order-2 flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300 md:order-1 md:ml-0">
          <Folder className="h-3 w-3 shrink-0 text-blue-500 dark:text-blue-400" />
          <span className="max-w-[120px] truncate md:max-w-[200px]">
            {workspace.name}
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => {
                  router.push("/");
                  router.refresh();
                }}
                className="ml-0.5 rounded-full p-0.5 hover:bg-muted transition-colors"
                aria-label="워크스페이스 나가기"
                type="button"
              >
                <X className="h-3 w-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent>워크스페이스 나가기</TooltipContent>
          </Tooltip>
        </div>
      )}

      {isAdmin && (
        <Button
          asChild
          className="order-3 ml-auto h-8 w-8 p-0 md:h-fit md:w-fit md:px-2"
          variant="ghost"
          size="icon"
          title="관리자"
        >
          <Link href="/admin">
            <Shield className="h-4 w-4" />
            <span className="sr-only">관리자</span>
          </Link>
        </Button>
      )}

      <Button
        className="relative order-4 h-8 w-8 p-0 md:h-fit md:w-fit md:px-2"
        onClick={openWhatsNew}
        variant="ghost"
        size="icon"
        title="새 기능"
      >
        <Sparkles className="h-4 w-4" />
        {hasUnseenAnnouncements && (
          <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-blue-500" />
        )}
        <span className="sr-only">새 기능</span>
      </Button>

      <Button
        className="order-5 h-8 w-8 p-0 md:h-fit md:w-fit md:px-2"
        onClick={openOnboarding}
        variant="ghost"
        size="icon"
        title="사용 가이드"
      >
        <HelpCircle className="h-4 w-4" />
        <span className="sr-only">사용 가이드</span>
      </Button>

      <Button
        className="order-6 h-8 w-8 p-0 md:h-fit md:w-fit md:px-2"
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        variant="outline"
        size="icon"
      >
        <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
        <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        <span className="sr-only">Toggle theme</span>
      </Button>

      {/* <Button
        asChild
        className="order-3 hidden bg-zinc-900 px-2 text-zinc-50 hover:bg-zinc-800 md:ml-auto md:flex md:h-fit dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
      >
        <Link
          href={"https://vercel.com/templates/next.js/nextjs-ai-chatbot"}
          rel="noreferrer"
          target="_noblank"
        >
          <VercelIcon size={16} />
          Deploy with Vercel
        </Link>
      </Button> */}
    </header>
  );
}

export const ChatHeader = memo(PureChatHeader, (prevProps, nextProps) => {
  return (
    prevProps.chatId === nextProps.chatId &&
    prevProps.isReadonly === nextProps.isReadonly &&
    prevProps.workspace?.uuid === nextProps.workspace?.uuid
  );
});
