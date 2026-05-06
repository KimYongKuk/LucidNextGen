"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ClipboardCheck, RefreshCw, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { agentApi, type Agent } from "@/lib/api/agents";
import { getUserId, isOperatorUser } from "@/lib/utils";
import { toast } from "sonner";

const STATUS_LABELS: Record<string, string> = {
  pending_review: "검증 진행 중",
  pending_approval: "승인 대기",
  rejected: "반려됨",
};

const STATUS_COLORS: Record<string, string> = {
  pending_review: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  pending_approval: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  rejected: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

const PLATFORM_LABELS: Record<string, string> = {
  miso: "MISO",
  runner: "Runner",
  webhook: "Webhook",
  native: "Native",
};

export default function AgentApprovalsPage() {
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const uid = getUserId();
    setAuthorized(isOperatorUser(uid));
  }, []);

  const fetchQueue = async () => {
    setLoading(true);
    try {
      const data = await agentApi.listApprovalQueue();
      setAgents(data);
    } catch (e: any) {
      toast.error(`승인 큐 조회 실패: ${e?.message ?? "오류"}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authorized) fetchQueue();
  }, [authorized]);

  if (authorized === null) {
    return <div className="p-8 text-sm text-muted-foreground">로딩 중...</div>;
  }
  if (!authorized) {
    return (
      <div className="mx-auto max-w-md p-8 text-center">
        <AlertCircle className="mx-auto h-10 w-10 text-amber-500" />
        <h2 className="mt-4 text-lg font-semibold">접근 제한</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          이 페이지는 관리자 전용입니다.
        </p>
        <Button asChild variant="ghost" className="mt-4">
          <Link href="/agent-store">Agent Store로</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between">
          <Button asChild variant="ghost" size="sm">
            <Link href="/agent-store">
              <ArrowLeft className="mr-1 h-4 w-4" />
              Agent Store로
            </Link>
          </Button>
          <Button onClick={fetchQueue} variant="outline" size="sm" disabled={loading}>
            <RefreshCw className={`mr-1 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            새로고침
          </Button>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/15">
            <ClipboardCheck className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Agent 승인 대기 큐</h1>
            <p className="text-sm text-muted-foreground">
              자동 검증 후 관리자 검토가 필요한 Agent 목록 (반려 포함, 재제출 가능)
            </p>
          </div>
        </div>

        {loading && agents.length === 0 ? (
          <div className="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground">
            큐 조회 중...
          </div>
        ) : agents.length === 0 ? (
          <div className="rounded-lg border border-dashed bg-muted/40 p-12 text-center">
            <ClipboardCheck className="mx-auto h-10 w-10 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">
              승인 대기 중인 Agent가 없습니다.
            </p>
          </div>
        ) : (
          <div className="rounded-lg border bg-card">
            <table className="w-full">
              <thead className="border-b bg-muted/40">
                <tr className="text-left text-xs uppercase text-muted-foreground">
                  <th className="px-4 py-3 font-medium">이름 / Slug</th>
                  <th className="px-4 py-3 font-medium">플랫폼</th>
                  <th className="px-4 py-3 font-medium">상태</th>
                  <th className="px-4 py-3 font-medium">버전</th>
                  <th className="px-4 py-3 font-medium">작성자</th>
                  <th className="px-4 py-3 font-medium">등록일</th>
                  <th className="px-4 py-3 font-medium" />
                </tr>
              </thead>
              <tbody>
                {agents.map((a) => (
                  <tr
                    key={a.id}
                    className="border-b text-sm transition-colors hover:bg-muted/20"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium">{a.icon ? `${a.icon} ` : ""}{a.name}</div>
                      <div className="text-xs text-muted-foreground">{a.slug}</div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="outline">{PLATFORM_LABELS[a.platform] ?? a.platform}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          STATUS_COLORS[a.status] ?? "bg-muted text-foreground"
                        }`}
                      >
                        {STATUS_LABELS[a.status] ?? a.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{a.version}</td>
                    <td className="px-4 py-3 text-xs">
                      {a.author_user_id}
                      {a.author_team && (
                        <span className="ml-1 text-muted-foreground">({a.author_team})</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {new Date(a.created_at).toLocaleDateString("ko-KR")}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button asChild size="sm" variant="outline">
                        <Link href={`/admin/agent-store/approvals/${a.slug}`}>검토</Link>
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          상태 안내: <b>검증 진행 중</b> = AI 자동 검증 실행 중 / <b>승인 대기</b> = 검증 통과, 관리자 결정 필요 / <b>반려됨</b> = 검증 실패 또는 관리자 반려, 작성자 수정 후 재제출 대기
        </p>
      </div>
    </div>
  );
}
