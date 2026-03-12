import { isToday, isYesterday, subMonths, subWeeks } from "date-fns";
import { color, motion } from "framer-motion";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import useSWRInfinite from "swr/infinite";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  useSidebar,
} from "@/components/ui/sidebar";
import { fetcher, getUserId } from "@/lib/utils";
import { LoaderIcon } from "./icons";
import { ChatItem } from "./sidebar-history-item";

export type Chat = {
  id: string;
  session_id?: string;
  title: string;
  createdAt: string;
  created_at?: string;
  updatedAt: string;
  updated_at?: string;
  chatMode: string;
  chat_mode?: string;
  isPinned?: boolean;
  is_pinned?: boolean;
};

export type ChatHistory = {
  chats: Chat[];
  hasMore: boolean;
  nextCursor?: string | null;
};

type GroupedChats = {
  pinned: Chat[];
  today: Chat[];
  past: Chat[];
};

const PAGE_SIZE = 10;

const groupChatsByDate = (chats: Chat[]): GroupedChats => {
  return chats.reduce(
    (groups, chat) => {
      // Handle potential snake_case from backend
      const isPinned = chat.isPinned || chat.is_pinned || false;

      if (isPinned) {
        groups.pinned.push(chat);
        return groups;
      }

      // Parse as local time (not UTC)
      // Use updatedAt (last activity) for grouping, not createdAt
      const dateStr = chat.updatedAt || chat.updated_at || chat.createdAt || chat.created_at;
      const chatDate = dateStr ? new Date(dateStr) : new Date();

      if (isToday(chatDate)) {
        groups.today.push(chat);
      } else {
        groups.past.push(chat);
      }

      return groups;
    },
    {
      pinned: [],
      today: [],
      past: [],
    } as GroupedChats
  );
};

export function getChatHistoryPaginationKey(
  pageIndex: number,
  previousPageData: ChatHistory,
  workspaceId?: string | null
) {
  if (previousPageData && previousPageData.hasMore === false) {
    return null;
  }

  // 워크스페이스 내에서는 기간 제한 없이 전체 조회
  const range = workspaceId ? "all" : undefined;

  if (pageIndex === 0) {
    const base = `/api/history?limit=${PAGE_SIZE}`;
    return range ? `${base}&range=${range}` : base;
  }

  const cursor = previousPageData.nextCursor;
  if (!cursor) return null;

  return `/api/history?limit=${PAGE_SIZE}&cursor=${encodeURIComponent(cursor)}&range=all`;
}

export function SidebarHistory() {
  const { setOpenMobile } = useSidebar();
  const { id } = useParams();
  const searchParams = useSearchParams();
  const workspaceId = searchParams.get("workspace_id");

  const userId = getUserId() ?? "";

  const {
    data: paginatedChatHistories,
    setSize,
    isValidating,
    isLoading,
    mutate,
  } = useSWRInfinite<ChatHistory>(
    (pageIndex, previousPageData) => {
      const base = getChatHistoryPaginationKey(pageIndex, previousPageData, workspaceId);
      if (!base) return null;
      const url = new URL(base, "http://localhost");
      url.searchParams.set("user_id", userId);

      // 워크스페이스 필터링 추가
      if (workspaceId) {
        url.searchParams.set("workspace_id", workspaceId);
      }

      return url.pathname + url.search;
    },
    fetcher,
    {
      fallbackData: [],
      revalidateFirstPage: true,
    }
  );

  const router = useRouter();
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const observerTarget = useRef<HTMLDivElement>(null);

  const chatsFromHistory = useMemo(() => {
    if (!paginatedChatHistories) return [] as Chat[];
    const allChats = paginatedChatHistories.flatMap((page) => page.chats);
    // Deduplicate by ID to prevent "duplicate key" errors
    const uniqueChats = Array.from(
      new Map(allChats.map((chat) => [chat.id || chat.session_id, chat])).values()
    );
    return uniqueChats;
  }, [paginatedChatHistories]);

  const hasReachedEnd = paginatedChatHistories
    ? paginatedChatHistories.some((page) => page.hasMore === false)
    : false;

  const hasEmptyChatHistory = paginatedChatHistories
    ? paginatedChatHistories.every((page) => page.chats.length === 0)
    : false;

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isValidating && !hasReachedEnd) {
          setSize((prev) => prev + 1);
        }
      },
      { threshold: 0.1 }
    );

    if (observerTarget.current) {
      observer.observe(observerTarget.current);
    }

    return () => observer.disconnect();
  }, [isValidating, hasReachedEnd, setSize]);

  const handleDelete = () => {
    const deletePromise = fetch(`/api/history?id=${deleteId}&user_id=${userId}`, {
      method: "DELETE",
    });

    toast.promise(deletePromise, {
      loading: "Deleting chat...",
      success: () => {
        mutate((chatHistories) => {
          if (chatHistories) {
            return chatHistories.map((chatHistory) => ({
              ...chatHistory,
              chats: chatHistory.chats.filter((chat) => chat.id !== deleteId),
            }));
          }
        });

        return "Chat deleted successfully";
      },
      error: "Failed to delete chat",
    });

    setShowDeleteDialog(false);

    if (deleteId === id) {
      router.push("/");
    }
  };

  const handleTogglePin = async (chatId: string, currentPinned: boolean) => {
    try {
      const response = await fetch(`/api/v1/chat/sessions/${chatId}/pin`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ is_pinned: !currentPinned }),
      });

      if (!response.ok) throw new Error("Failed to toggle pin");

      mutate((chatHistories) => {
        if (!chatHistories) return chatHistories;
        return chatHistories.map((page) => ({
          ...page,
          chats: page.chats.map((chat) => {
            const id = chat.id || chat.session_id;
            if (id === chatId) {
              return {
                ...chat,
                is_pinned: !currentPinned,
                isPinned: !currentPinned,
              };
            }
            return chat;
          }),
        }));
      });

      toast.success(currentPinned ? "Chat unpinned" : "Chat pinned");
    } catch (error) {
      toast.error("Failed to update pin status");
    }
  };

  if (isLoading) {
    return (
      <SidebarGroup>
        <div className="px-2 py-1 text-sidebar-foreground/50 text-xs">
          Today
        </div>
        <SidebarGroupContent>
          <div className="flex flex-col">
            {[44, 32, 28, 64, 52].map((item) => (
              <div
                className="flex h-8 items-center gap-2 rounded-md px-2"
                key={item}
              >
                <div
                  className="h-4 max-w-(--skeleton-width) flex-1 rounded-md bg-sidebar-accent-foreground/10"
                  style={{
                    ["--skeleton-width" as string]: `${item}%`,
                  } as React.CSSProperties}
                />
              </div>
            ))}
          </div>
        </SidebarGroupContent>
      </SidebarGroup>
    );
  }

  if (hasEmptyChatHistory) {
    return (
      <SidebarGroup>
        <SidebarGroupContent>
          <div className="flex w-full flex-row items-center justify-center gap-2 px-2 text-sm text-zinc-500">
            Your conversations will appear here once you start chatting!
          </div>
        </SidebarGroupContent>
      </SidebarGroup>
    );
  }

  const groupedChats = groupChatsByDate(chatsFromHistory);

  return (
    <>
      <SidebarGroup>
        <SidebarGroupContent>
          <SidebarMenu>
            <div className="flex flex-col gap-6">
              {groupedChats.pinned.length > 0 && (
                <div>
                  <div className="px-2 py-1 text-sidebar-foreground/50 text-xs">
                    <b className="text-[#FF4000]">고정됨</b>
                  </div>
                  {groupedChats.pinned.map((chat) => {
                    const chatId = chat.id || chat.session_id || "";
                    return (
                      <ChatItem
                        chat={chat}
                        isActive={chatId === id}
                        key={chatId}
                        onDelete={(id) => {
                          setDeleteId(id);
                          setShowDeleteDialog(true);
                        }}
                        onTogglePin={(id) => handleTogglePin(id, true)}
                        isPinned={true}
                        setOpenMobile={setOpenMobile}
                      />
                    );
                  })}
                </div>
              )}

              {groupedChats.today.length > 0 && (
                <div>
                  <div className="px-2 py-1 text-sidebar-foreground/50 text-xs">
                    <b className="text-[#FF4000]">Today</b>
                  </div>
                  {groupedChats.today.map((chat) => {
                    const chatId = chat.id || chat.session_id || "";
                    return (
                      <ChatItem
                        chat={chat}
                        isActive={chatId === id}
                        key={chatId}
                        onDelete={(id) => {
                          setDeleteId(id);
                          setShowDeleteDialog(true);
                        }}
                        onTogglePin={(id) => handleTogglePin(id, false)}
                        isPinned={false}
                        setOpenMobile={setOpenMobile}
                      />
                    );
                  })}
                </div>
              )}

              {groupedChats.past.length > 0 && (
                <div>
                  <div className="px-2 py-1 text-sidebar-foreground/50 text-xs">
                    <b className="text-[#FF4000]">Past</b>
                  </div>
                  {groupedChats.past.map((chat) => {
                    const chatId = chat.id || chat.session_id || "";
                    return (
                      <ChatItem
                        chat={chat}
                        isActive={chatId === id}
                        key={chatId}
                        onDelete={(id) => {
                          setDeleteId(id);
                          setShowDeleteDialog(true);
                        }}
                        onTogglePin={(id) => handleTogglePin(id, false)}
                        isPinned={false}
                        setOpenMobile={setOpenMobile}
                      />
                    );
                  })}
                </div>
              )}
            </div>

            <div ref={observerTarget} className="mt-4 h-4 w-full" />

            {!hasReachedEnd && isValidating && (
              <div className="flex flex-row items-center justify-center gap-2 p-2 text-zinc-500 dark:text-zinc-400">
                <div className="animate-spin">
                  <LoaderIcon />
                </div>
                <div className="text-xs">Loading more...</div>
              </div>
            )}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <AlertDialog onOpenChange={setShowDeleteDialog} open={showDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete your
              chat and remove it from our servers.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>
              Continue
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
