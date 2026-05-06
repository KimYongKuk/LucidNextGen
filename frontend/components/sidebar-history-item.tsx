import Link from "next/link";
import { memo } from "react";
import { Clock } from "lucide-react";
// import type { Chat } from "@/lib/db/schema";
import {
  MoreHorizontalIcon,
  TrashIcon,
  PinIcon,
} from "./icons";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import {
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
} from "./ui/sidebar";

type Chat = {
  id: string;
  title: string;
  // Phase 3b: cron 자동 생성 세션이면 시계 아이콘 + 살짝 다른 톤으로 구분
  auto_generated?: boolean | number;
};

const PureChatItem = ({
  chat,
  isActive,
  onDelete,
  onTogglePin,
  isPinned,
  setOpenMobile,
  workspaceId,
}: {
  chat: Chat;
  isActive: boolean;
  onDelete: (chatId: string) => void;
  onTogglePin?: (chatId: string) => void;
  isPinned?: boolean;
  setOpenMobile: (open: boolean) => void;
  workspaceId?: string | null;
}) => {
  const href = workspaceId
    ? `/chat/${chat.id}?workspace_id=${workspaceId}`
    : `/chat/${chat.id}`;
  const isAuto = !!chat.auto_generated;
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        asChild
        isActive={isActive}
        title={isAuto ? "스케줄러가 자동 생성한 세션입니다" : undefined}
      >
        <Link href={href} onClick={() => setOpenMobile(false)} className="flex items-center gap-1.5">
          {isAuto && (
            <Clock className="h-3.5 w-3.5 shrink-0 text-blue-500 dark:text-blue-400" aria-label="자동 실행" />
          )}
          <span className="truncate">{chat.title}</span>
        </Link>
      </SidebarMenuButton>

      <DropdownMenu modal={true}>
        <DropdownMenuTrigger asChild>
          <SidebarMenuAction
            className="mr-0.5 data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            showOnHover={!isActive}
          >
            <MoreHorizontalIcon />
            <span className="sr-only">More</span>
          </SidebarMenuAction>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" side="bottom">
          {onTogglePin && (
            <DropdownMenuItem
              className="cursor-pointer"
              onSelect={() => onTogglePin(chat.id)}
            >
              <PinIcon />
              <span>{isPinned ? "Unpin" : "Pin"}</span>
            </DropdownMenuItem>
          )}
          <DropdownMenuItem
            className="cursor-pointer text-destructive focus:bg-destructive/15 focus:text-destructive dark:text-red-500"
            onSelect={() => onDelete(chat.id)}
          >
            <TrashIcon />
            <span>Delete</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  );
};

export const ChatItem = memo(PureChatItem, (prevProps, nextProps) => {
  if (prevProps.isActive !== nextProps.isActive) {
    return false;
  }
  if (prevProps.isPinned !== nextProps.isPinned) {
    return false;
  }
  if (prevProps.workspaceId !== nextProps.workspaceId) {
    return false;
  }
  return true;
});
