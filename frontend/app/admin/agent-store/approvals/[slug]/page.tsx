"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, AlertCircle, CheckCircle2, XCircle, AlertTriangle, FileSearch, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { agentApi, type Agent, type AgentReviewReport } from "@/lib/api/agents";
import { getUserId, isOperatorUser } from "@/lib/utils";
import { toast } from "sonner";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-800 border-red-300 dark:bg-red-950 dark:text-red-300",
  error: "bg-orange-100 text-orange-800 border-orange-300 dark:bg-orange-950 dark:text-orange-300",
  warn: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-950 dark:text-amber-300",
  info: "bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-950 dark:text-blue-300",
};

const STATUS_COLORS: Record<string, string> = {
  passed: "bg-green-100 text-green-800",
  warnings: "bg-amber-100 text-amber-800",
  failed: "bg-red-100 text-red-800",
};

export default function AgentApprovalDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const router = useRouter();
  const { slug } = use(params);
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [reports, setReports] = useState<AgentReviewReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const uid = getUserId();
    setAuthorized(isOperatorUser(uid));
  }, []);

  useEffect(() => {
    if (!authorized) return;
    (async () => {
      setLoading(true);
      try {
        const [a, r] = await Promise.all([
          agentApi.get(slug),
          agentApi.listReviews(slug),
        ]);
        setAgent(a);
        setReports(r);
      } catch (e: any) {
        toast.error(`조회 실패: ${e?.message ?? "오류"}`);
      } finally {
        setLoading(false);
      }
    })();
  }, [slug, authorized]);

  const handleDecision = async (decision: "approved" | "rejected" | "request_changes") => {
    if (!agent) return;
    setSubmitting(true);
    try {
      const result = await agentApi.submitApproval(
        slug,
        decision,
        comment.trim() || undefined,
        reports.map((r) => r.id),
      );
      const labels = {
        approved: "승인",
        rejected: "반려",
        request_changes: "변경 요청",
      };
      toast.success(`'${agent.name}' ${labels[decision]} — 새 상태: ${result.new_status}`);
      router.push("/admin/agent-store/approvals");
    } catch (e: any) {
      toast.error(`결정 실패: ${e?.message ?? "오류"}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (authorized === null) {
    return <div className="p-8 text-sm text-muted-foreground">로딩 중...</div>;
  }
  if (!authorized) {
    return (
      <div className="mx-auto max-w-md p-8 text-center">
        <AlertCircle className="mx-auto h-10 w-10 text-amber-500" />
        <h2 className="mt-4 text-lg font-semibold">접근 제한</h2>
        <p className="mt-2 text-sm text-muted-foreground">관리자 전용 페이지입니다.</p>
      </div>
    );
  }
  if (loading) {
    return <div className="p-8 text-sm text-muted-foreground">불러오는 중...</div>;
  }
  if (!agent) {
    return <div className="p-8 text-sm">Agent를 찾을 수 없습니다.</div>;
  }

  // 카테고리별 최신 리포트 분리
  const latestQuality = reports.find((r) => r.category === "quality");
  const latestSecurity = reports.find((r) => r.category === "security");

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6">
        <Button asChild variant="ghost" size="sm" className="self-start">
          <Link href="/admin/agent-store/approvals">
            <ArrowLeft className="mr-1 h-4 w-4" />
            승인 큐로
          </Link>
        </Button>

        {/* Agent 메타 */}
        <div className="rounded-xl border bg-card p-6">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/15 text-2xl">
              {agent.icon || <Bot className="h-6 w-6" />}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold">{agent.name}</h1>
                <Badge variant="outline">{agent.platform}</Badge>
                <Badge>{agent.status}</Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{agent.slug} · v{agent.version}</p>
              <p className="mt-3 text-sm">{agent.description}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {agent.capabilities.map((c) => (
                  <Badge key={c} variant="secondary" className="text-[11px]">
                    {c}
                  </Badge>
                ))}
                {agent.tags?.map((t) => (
                  <Badge key={t} variant="outline" className="text-[11px]">
                    #{t}
                  </Badge>
                ))}
              </div>
              <div className="mt-3 text-xs text-muted-foreground">
                작성자: {agent.author_user_id} {agent.author_team && `(${agent.author_team})`} · 공개: {agent.visibility}
              </div>
            </div>
          </div>
        </div>

        {/* 검증 리포트 */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <ReportCard title="Quality 검증" report={latestQuality} />
          <ReportCard title="Security 검증" report={latestSecurity} />
        </div>

        {/* 매니페스트 (raw) */}
        <details className="rounded-lg border bg-card p-4">
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
            <FileSearch className="h-4 w-4" />
            Manifest (raw JSON)
          </summary>
          <pre className="mt-3 overflow-auto rounded bg-muted p-3 text-xs">
            {JSON.stringify(agent.manifest, null, 2)}
          </pre>
        </details>

        {/* 결정 */}
        <div className="rounded-xl border bg-card p-6">
          <h2 className="mb-3 text-base font-semibold">결정</h2>
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="(선택) 결정 사유를 작성자에게 전달합니다"
            rows={3}
            className="mb-4"
          />
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => handleDecision("approved")}
              disabled={submitting}
              className="bg-green-600 text-white hover:bg-green-700"
            >
              <CheckCircle2 className="mr-1.5 h-4 w-4" />
              승인 (active로 활성화)
            </Button>
            <Button
              onClick={() => handleDecision("request_changes")}
              disabled={submitting}
              variant="outline"
            >
              <AlertTriangle className="mr-1.5 h-4 w-4" />
              변경 요청
            </Button>
            <Button
              onClick={() => handleDecision("rejected")}
              disabled={submitting}
              variant="destructive"
            >
              <XCircle className="mr-1.5 h-4 w-4" />
              반려
            </Button>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            <b>승인</b>: status='active' (카탈로그 노출 + 실행 가능) / <b>변경 요청·반려</b>: status='rejected' (작성자 수정 후 재제출 대기)
          </p>
        </div>
      </div>
    </div>
  );
}

function ReportCard({ title, report }: { title: string; report?: AgentReviewReport }) {
  if (!report) {
    return (
      <div className="rounded-lg border bg-card p-4">
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="mt-2 text-xs text-muted-foreground">아직 리포트 없음 (검증 진행 중)</p>
      </div>
    );
  }
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            STATUS_COLORS[report.status] ?? ""
          }`}
        >
          {report.status}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
        <span>점수: <b className="text-foreground">{report.score ?? "-"}</b>/100</span>
        <span>최대 심각도: <b className="text-foreground">{report.severity_max}</b></span>
        <span>{new Date(report.created_at).toLocaleString("ko-KR")}</span>
      </div>
      {report.findings.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">발견된 이슈 없음</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {report.findings.map((f, i) => (
            <li
              key={i}
              className={`rounded border p-2 text-xs ${
                SEVERITY_COLORS[f.severity] ?? "bg-muted"
              }`}
            >
              <div className="flex items-center gap-1.5">
                <Badge variant="outline" className="text-[10px]">
                  {f.severity}
                </Badge>
                <Badge variant="outline" className="text-[10px]">
                  {f.category}
                </Badge>
              </div>
              <p className="mt-1.5">{f.message}</p>
              {f.suggestion && (
                <p className="mt-1 italic opacity-80">→ {f.suggestion}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
