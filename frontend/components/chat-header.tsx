"use client";

import { useRouter } from "next/navigation";
import { memo, useState } from "react";
import { useWindowSize } from "usehooks-ts";
import { useTheme } from "next-themes";
import { SidebarToggle } from "@/components/sidebar-toggle";
import { Button } from "@/components/ui/button";
import { PlusIcon } from "./icons";
import { useSidebar } from "./ui/sidebar";
import { HelpCircle, MessageSquare, Moon, Sun } from "lucide-react";
import { useOnboarding } from "@/components/onboarding/onboarding-provider";
import { FeedbackModal } from "@/components/feedback-modal";

function PureChatHeader({
  chatId,
  isReadonly,
}: {
  chatId: string;
  isReadonly: boolean;
}) {
  const router = useRouter();
  const { open } = useSidebar();
  const { theme, setTheme } = useTheme();
  const { openOnboarding } = useOnboarding();
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);

  const { width: windowWidth } = useWindowSize();

  return (
    <header className="sticky top-0 flex items-center gap-2 bg-background px-2 py-1.5 md:px-2">
      <SidebarToggle />

      {(!open || windowWidth < 768) && (
        <Button
          className="order-2 ml-auto h-8 px-2 md:order-1 md:ml-0 md:h-fit md:px-2"
          onClick={() => {
            router.push("/");
            router.refresh();
          }}
          variant="outline"
        >
          <PlusIcon />
          <span className="md:sr-only">New Chat</span>
        </Button>
      )}

      <Button
        className="order-3 ml-auto h-8 w-8 p-0 md:h-fit md:w-fit md:px-2"
        onClick={() => setShowFeedbackModal(true)}
        variant="ghost"
        size="icon"
        title="피드백"
      >
        <MessageSquare className="h-4 w-4" />
        <span className="sr-only">피드백</span>
      </Button>

      <Button
        className="order-4 h-8 w-8 p-0 md:h-fit md:w-fit md:px-2"
        onClick={openOnboarding}
        variant="ghost"
        size="icon"
        title="사용 가이드"
      >
        <HelpCircle className="h-4 w-4" />
        <span className="sr-only">사용 가이드</span>
      </Button>

      <Button
        className="order-5 h-8 w-8 p-0 md:h-fit md:w-fit md:px-2"
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        variant="outline"
        size="icon"
      >
        <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
        <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        <span className="sr-only">Toggle theme</span>
      </Button>

      <FeedbackModal
        open={showFeedbackModal}
        onOpenChange={setShowFeedbackModal}
      />

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
    prevProps.isReadonly === nextProps.isReadonly
  );
});
