"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Search, X, Loader2, MessageSquare } from "lucide-react";
import useSWR from "swr";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn, fetcher, getUserId } from "@/lib/utils";
import { useDebounce } from "@/hooks/use-debounce";
import { useSidebar } from "@/components/ui/sidebar";

type Chat = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  chatMode: string;
  isPinned?: boolean;
  workspace_id?: string;  // UUID string
};

interface ChatSearchModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChatSearchModal({ open, onOpenChange }: ChatSearchModalProps) {
  const router = useRouter();
  const { setOpenMobile } = useSidebar();
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedQuery = useDebounce(searchQuery, 300);

  const userId = getUserId() ?? "";

  // Fetch recent chats when no search query
  const recentUrl =
    debouncedQuery === ""
      ? `/api/history?user_id=${encodeURIComponent(userId)}&range=recent7&limit=20`
      : null;

  // Search URL when there is a query
  const searchUrl =
    debouncedQuery !== ""
      ? `/api/history/search?user_id=${encodeURIComponent(userId)}&q=${encodeURIComponent(debouncedQuery)}&limit=20`
      : null;

  const { data: recentData, isLoading: isLoadingRecent } = useSWR<{
    chats: Chat[];
  }>(recentUrl, fetcher);

  const { data: searchData, isLoading: isLoadingSearch } = useSWR<{
    chats: Chat[];
    query: string;
  }>(searchUrl, fetcher);

  const isSearching = debouncedQuery !== "";
  const isLoading = isSearching ? isLoadingSearch : isLoadingRecent;
  const chats = isSearching ? searchData?.chats : recentData?.chats;

  // Reset search when modal closes
  useEffect(() => {
    if (!open) {
      setSearchQuery("");
    }
  }, [open]);

  const handleSelectChat = (chat: Chat) => {
    setOpenMobile(false);
    onOpenChange(false);

    // workspace_id가 있으면 포함하여 이동
    const url = chat.workspace_id
      ? `/chat/${chat.id}?workspace_id=${chat.workspace_id}`
      : `/chat/${chat.id}`;

    router.push(url);
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return formatDistanceToNow(date, { addSuffix: true, locale: ko });
    } catch {
      return "";
    }
  };

  const highlightMatch = (text: string, query: string) => {
    if (!query || !text) return text;

    const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(`(${escapedQuery})`, "gi");
    const parts = text.split(regex);

    return parts.map((part, i) =>
      regex.test(part) ? (
        <mark key={i} className="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5">
          {part}
        </mark>
      ) : (
        part
      )
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[70vh] flex flex-col p-0 gap-0">
        <DialogHeader className="p-4 pb-0">
          <DialogTitle>채팅 검색</DialogTitle>
        </DialogHeader>

        {/* Search Input */}
        <div className="p-4 border-b">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="검색어를 입력하세요..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-9"
              autoFocus
            />
            {searchQuery && (
              <Button
                variant="ghost"
                size="icon"
                className="absolute right-1 top-1/2 transform -translate-y-1/2 h-7 w-7"
                onClick={() => setSearchQuery("")}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        {/* Results */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : chats && chats.length > 0 ? (
            <div className="space-y-1">
              {!isSearching && (
                <p className="text-xs text-muted-foreground mb-3 font-medium">
                  최근 일주일
                </p>
              )}
              {isSearching && (
                <p className="text-xs text-muted-foreground mb-3 font-medium">
                  검색 결과 ({chats.length}건)
                </p>
              )}
              {chats.map((chat) => (
                <button
                  key={chat.id}
                  onClick={() => handleSelectChat(chat)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-left",
                    "hover:bg-accent transition-colors",
                    "focus:outline-none focus:ring-2 focus:ring-ring"
                  )}
                >
                  <MessageSquare className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm truncate">
                      {isSearching
                        ? highlightMatch(chat.title, debouncedQuery)
                        : chat.title}
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground flex-shrink-0">
                    {formatDate(chat.updatedAt || chat.createdAt)}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <MessageSquare className="h-10 w-10 text-muted-foreground/50 mb-3" />
              <p className="text-sm text-muted-foreground">
                {isSearching
                  ? "검색 결과가 없습니다"
                  : "최근 채팅이 없습니다"}
              </p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
