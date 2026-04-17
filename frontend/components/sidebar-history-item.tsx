import Link from "next/link";
import { memo } from "react";
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
  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={isActive}>
        <Link href={href} onClick={() => setOpenMobile(false)}>
          <span>{chat.title}</span>
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
