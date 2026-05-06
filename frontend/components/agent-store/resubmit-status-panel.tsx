"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, XCircle, RefreshCw, Pencil, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { agentApi, type Agent as BackendAgent, type AgentReviewReport } from "@/lib/api/agents";

interface ApprovalRow {
  id: string;
  agent_id: string;
  agent_version: string;
  approver_user_id: string;
  decision: "approved" | "rejected" | "request_changes";
  comment?: string;
  decided_at: string;
}

interface Props {
  slug: string;
  isAuthor: boolean;
  onUpdated?: () => void;
}

const STATUS_LABEL: Record<string, string> = {
  pending_review: "검증 진행 중",
  pending_approval: "승인 대기",
  rejected: "반려됨 (수정 후 재제출 필요)",
};

export function ResubmitStatusPanel({ slug, isAuthor, onUpdated }: Props) {
  const [agent, setAgent] = useState<BackendAgent | null>(null);
  const [reports, setReports] = useState<AgentReviewReport[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRow[]>([]);
  const [loading, setLoading] = useState(true);

  const [editOpen, setEditOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editSystemPrompt, setEditSystemPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const [a, r, ap] = await Promise.all([
        agentApi.get(slug),
        agentApi.listReviews(slug).catch(() => []),
        agentApi.listApprovals(slug).catch(() => []),
      ]);
      setAgent(a);
      setReports(r);
      setApprovals(ap);
      setEditName(a.name);
      setEditDescription(a.description);
      setEditSystemPrompt(((a.manifest as any)?.intent_hints?.system_prompt) ?? "");
    } catch (e: any) {
      toast.error(`상태 조회 실패: ${e?.message ?? "오류"}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [slug]);

  if (loading || !agent) return null;

  // 진행 중/반려 상태에서만 표시 (active이면 박스 X)
  const showPanel = ["pending_review", "pending_approval", "rejected"].includes(agent.status);
  if (!showPanel) return null;

  const latestApproval = approvals[0];
  const latestReports = {
    quality: reports.find((r) => r.category === "quality"),
    security: reports.find((r) => r.category === "security"),
  };

  const handleResubmit = async () => {
    setSubmitting(true);
    try {
      const updatedManifest = {
        ...(agent.manifest as any),
        intent_hints: {
          ...((agent.manifest as any)?.intent_hints ?? {}),
          system_prompt: editSystemPrompt,
        },
      };
      await agentApi.update(slug, {
        name: editName,
        description: editDescription,
        manifest: updatedManifest,
      } as any);
      toast.success("수정 완료 — 재검증 + 관리자 승인 대기 중");
      setEditOpen(false);
      await refresh();
      onUpdated?.();
    } catch (e: any) {
      toast.error(`수정 실패: ${e?.message ?? "오류"}`);
    } finally {
      setSubmitting(false);
    }
  };

  const isRejected = agent.status === "rejected";
  const accentClass = isRejected
    ? "border-red-300 bg-red-50/50 dark:border-red-900 dark:bg-red-950/30"
    : "border-amber-300 bg-amber-50/50 dark:border-amber-900 dark:bg-amber-950/30";
  const Icon = isRejected ? XCircle : AlertTriangle;
  const iconClass = isRejected ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400";

  return (
    <div className={`mt-6 rounded-lg border p-4 ${accentClass}`}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${iconClass}`} />
        <div className="flex-1 space-y-3">
          <div>
            <p className="text-sm font-semibold">
              상태: {STATUS_LABEL[agent.status] ?? agent.status} (v{agent.version})
            </p>
          </div>

          {/* 관리자 결정 코멘트 */}
          {latestApproval && (
            <div className="rounded-md bg-background/50 p-3 text-xs">
              <p className="font-medium">
                관리자 결정:{" "}
                <span className="font-semibold">
                  {latestApproval.decision === "approved" ? "✅ 승인" : ""}
                  {latestApproval.decision === "rejected" ? "❌ 반려" : ""}
                  {latestApproval.decision === "request_changes" ? "⚠ 변경 요청" : ""}
                </span>
              </p>
              {latestApproval.comment && (
                <p className="mt-1.5 whitespace-pre-wrap text-muted-foreground">
                  &ldquo;{latestApproval.comment}&rdquo;
                </p>
              )}
              <p className="mt-1.5 text-[10px] text-muted-foreground">
                {new Date(latestApproval.decided_at).toLocaleString("ko-KR")}
              </p>
            </div>
          )}

          {/* AI 검증 요약 */}
          {(latestReports.quality || latestReports.security) && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {latestReports.quality && (
                <CompactReportSummary title="Quality 검증" report={latestReports.quality} />
              )}
              {latestReports.security && (
                <CompactReportSummary title="Security 검증" report={latestReports.security} />
              )}
            </div>
          )}

          {/* 작성자용 액션 */}
          {isAuthor && (
            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" onClick={() => setEditOpen(true)}>
                <Pencil className="mr-1.5 h-3.5 w-3.5" />
                수정 후 재제출
              </Button>
              <Button size="sm" variant="outline" onClick={refresh}>
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                상태 새로고침
              </Button>
            </div>
          )}
          {!isAuthor && (
            <p className="text-[11px] text-muted-foreground">
              작성자만 수정 후 재제출할 수 있습니다.
            </p>
          )}
        </div>
      </div>

      {/* 수정 모달 */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Agent 수정 후 재제출</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">이름</label>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">설명</label>
              <Textarea
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                rows={2}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">라우팅 안내 (시스템 프롬프트)</label>
              <Textarea
                value={editSystemPrompt}
                onChange={(e) => setEditSystemPrompt(e.target.value)}
                rows={4}
              />
              <p className="text-[11px] text-muted-foreground">
                이 Agent를 언제 호출할지 안내. 저장 시 자동으로 재검증되고 관리자 승인 대기로 들어갑니다.
              </p>
            </div>
            <p className="rounded-md border border-blue-200 bg-blue-50/50 p-2 text-[11px] text-blue-900 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-200">
              ℹ MISO 키나 Runner 매크로 등 플랫폼별 설정은 이 화면에서 수정할 수 없습니다. 변경이 필요하면 별도 등록 위저드를 활용해주세요.
            </p>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditOpen(false)}>
              취소
            </Button>
            <Button onClick={handleResubmit} disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  재제출 중...
                </>
              ) : (
                "수정 + 재제출"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CompactReportSummary({ title, report }: { title: string; report: AgentReviewReport }) {
  const statusColor =
    report.status === "passed"
      ? "text-green-700 dark:text-green-400"
      : report.status === "warnings"
        ? "text-amber-700 dark:text-amber-400"
        : "text-red-700 dark:text-red-400";
  return (
    <div className="rounded-md bg-background/50 p-2.5 text-[11px]">
      <div className="flex items-center justify-between">
        <span className="font-semibold">{title}</span>
        <span className={statusColor}>{report.status}</span>
      </div>
      {report.findings.length > 0 ? (
        <ul className="mt-1 ml-3 list-disc space-y-0.5 text-muted-foreground">
          {report.findings.slice(0, 3).map((f, i) => (
            <li key={i}>
              <span className="font-medium">[{f.severity}]</span> {f.message}
            </li>
          ))}
          {report.findings.length > 3 && (
            <li className="opacity-70">… +{report.findings.length - 3}건</li>
          )}
        </ul>
      ) : (
        <p className="mt-1 text-muted-foreground">발견된 이슈 없음</p>
      )}
    </div>
  );
}
