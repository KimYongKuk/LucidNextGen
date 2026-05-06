"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  CommonMetaSection,
  DEFAULT_META,
  buildCommonManifest,
  parseTags,
  validateCommon,
  getAutoIcon,
  type CommonMeta,
} from "@/components/agent-store/new-agent-common";
import { agentApi } from "@/lib/api/agents";

const EXECUTORS = ["pad", "python", "vbs", "bat", "ps1"] as const;

export default function NewRunnerAgentPage() {
  const router = useRouter();
  const [meta, setMeta] = useState<CommonMeta>(DEFAULT_META);
  const [runnerId, setRunnerId] = useState("");
  const [requiredLabels, setRequiredLabels] = useState("sap-fi, office");
  const [executor, setExecutor] = useState<(typeof EXECUTORS)[number]>("pad");
  const [entry, setEntry] = useState("");
  const [argsRaw, setArgsRaw] = useState("");
  const [timeout, setTimeoutSec] = useState(300);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    const err = validateCommon(meta);
    if (err) {
      toast.error(err);
      return;
    }
    if (!runnerId.trim()) {
      toast.error("Runner ID는 필수입니다.");
      return;
    }
    if (!entry.trim()) {
      toast.error("매크로 entry 경로는 필수입니다.");
      return;
    }

    const labels = requiredLabels
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const args = argsRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const manifest = {
      ...buildCommonManifest(meta),
      runtime: {
        platform: "runner",
        required_labels: labels,
        executor,
        entry: entry.trim(),
        args,
        timeout,
      },
      output: { type: "file" },
    };

    setSubmitting(true);
    try {
      const created = await agentApi.create({
        slug: meta.slug,
        name: meta.name,
        description: meta.description,
        platform: "runner",
        capabilities: meta.capabilities,
        manifest,
        visibility: meta.visibility,
        icon: getAutoIcon("runner"),
        tags: meta.tags ? parseTags(meta.tags) : undefined,
        runner_id: runnerId.trim(),
      });
      toast.success(`'${created.name}' 등록 완료 — 자동 검증 + 관리자 승인 대기`);
      router.push(`/agent-store/${created.slug}`);
    } catch (e: any) {
      toast.error(`등록 실패: ${e?.message ?? "알 수 없는 오류"}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6">
        <div>
          <Button asChild variant="ghost" size="sm">
            <Link href="/agent-store/new">
              <ArrowLeft className="mr-1 h-4 w-4" />
              플랫폼 선택으로
            </Link>
          </Button>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-300">
            <Lock className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Runner 매크로 등록</h1>
            <p className="text-sm text-muted-foreground">
              EC2 Runner에서 실행되는 매크로(PAD/Python/VBS 등) 등록 — 관리자 전용.
            </p>
          </div>
        </div>

        <div className="space-y-6 rounded-xl border bg-card p-6">
          <section className="space-y-3">
            <h2 className="text-base font-semibold">Runner 실행 정보</h2>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Runner ID *</label>
                <Input
                  value={runnerId}
                  onChange={(e) => setRunnerId(e.target.value)}
                  placeholder="runners 테이블 UUID"
                />
                <p className="text-[11px] text-muted-foreground">
                  4대 본부별 Runner 중 선택. 추후 드롭다운으로 개선 예정.
                </p>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Executor *</label>
                <Select value={executor} onValueChange={(v) => setExecutor(v as any)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EXECUTORS.map((e) => (
                      <SelectItem key={e} value={e}>
                        {e}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">Required Labels (쉼표 구분)</label>
              <Input
                value={requiredLabels}
                onChange={(e) => setRequiredLabels(e.target.value)}
                placeholder="sap-fi, office"
              />
              <p className="text-[11px] text-muted-foreground">
                Hub Router가 매칭되는 Runner를 자동 선택할 때 사용
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">매크로 Entry 경로 *</label>
              <Input
                value={entry}
                onChange={(e) => setEntry(e.target.value)}
                placeholder="monthly_close.flow (절대경로/상위경로 금지)"
              />
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">인자 (쉼표 구분, 템플릿 가능)</label>
                <Input
                  value={argsRaw}
                  onChange={(e) => setArgsRaw(e.target.value)}
                  placeholder="{{year_month}}, {{factory}}"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Timeout (초)</label>
                <Input
                  type="number"
                  value={timeout}
                  onChange={(e) => setTimeoutSec(parseInt(e.target.value || "300", 10))}
                  min={10}
                  max={3600}
                />
              </div>
            </div>
          </section>

          <hr className="border-border" />

          <section className="space-y-3">
            <h2 className="text-base font-semibold">기본 메타 + 분류</h2>
            <CommonMetaSection meta={meta} onChange={setMeta} platform="runner" />
          </section>

          <hr className="border-border" />

          <div className="flex justify-end gap-2">
            <Button asChild variant="ghost">
              <Link href="/agent-store/new">취소</Link>
            </Button>
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting ? "등록 중..." : "등록하기"}
            </Button>
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground">
          ⚠ 보안 검증: Path Traversal · 명령어 주입 · Secret Leak 자동 차단됩니다.
        </p>
      </div>
    </div>
  );
}
