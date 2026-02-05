"use client";

import useSWR from "swr";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";
import { MessageSquare, Clock } from "lucide-react";

import { Workspace } from "@/lib/api/workspaces";
import { getUserId } from "@/lib/utils";
import { fetcher } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

interface WorkspaceRecentHistoryProps {
    workspace: Workspace;
}

interface ChatSession {
    session_id: string;
    title: string;
    updated_at: string;
    message_count: number;
}

export function WorkspaceRecentHistory({ workspace }: WorkspaceRecentHistoryProps) {
    const userId = getUserId() ?? "";

    console.log("[WorkspaceRecentHistory] workspace:", workspace);
    const url = userId && workspace
        ? `/api/v1/chat/sessions?user_id=${userId}&workspace_id=${workspace.id}&limit=4`
        : null;
    console.log("[WorkspaceRecentHistory] SWR URL:", url);

    const { data, isLoading } = useSWR<{ sessions: ChatSession[] }>(
        url,
        fetcher
    );

    if (isLoading) {
        return (
            <div className="grid gap-4 md:grid-cols-2">
                {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} className="h-24 w-full rounded-lg" />
                ))}
            </div>
        );
    }

    const sessions = data?.sessions || [];

    if (sessions.length === 0) {
        return (
            <div className="text-center text-muted-foreground py-8">
                <p>아직 이 워크스페이스와 나눈 대화가 없습니다.</p>
                <p className="text-sm mt-1">새로운 주제로 대화를 시작해보세요!</p>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <h3 className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <Clock className="h-4 w-4" />
                최근 대화
            </h3>
            <div className="grid gap-4 md:grid-cols-2">
                {sessions.map((session) => (
                    <Link
                        key={session.session_id}
                        href={`/chat/${session.session_id}`}
                        className="group relative flex flex-col gap-2 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
                    >
                        <div className="flex items-center justify-between">
                            <span className="font-medium truncate group-hover:text-primary transition-colors">
                                {session.title || "새 대화"}
                            </span>
                            <MessageSquare className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                        <div className="text-xs text-muted-foreground">
                            {formatDistanceToNow(new Date(session.updated_at), {
                                addSuffix: true,
                                locale: ko,
                            })}
                            {" · "}
                            메시지 {session.message_count}개
                        </div>
                    </Link>
                ))}
            </div>
        </div>
    );
}
