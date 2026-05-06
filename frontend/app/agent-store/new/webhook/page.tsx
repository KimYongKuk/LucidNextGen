"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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

export default function NewWebhookAgentPage() {
  const router = useRouter();
  const [meta, setMeta] = useState<CommonMeta>(DEFAULT_META);
  const [method, setMethod] = useState<"POST" | "GET" | "PUT">("POST");
  const [url, setUrl] = useState("");
  const [authRef, setAuthRef] = useState("");
  const [requestMappingRaw, setRequestMappingRaw] = useState(`{
  "channel": "{{channel}}",
  "text": "{{message}}"
}`);
  const [responseMappingRaw, setResponseMappingRaw] = useState(`{
  "result": "{{response}}"
}`);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    const err = validateCommon(meta);
    if (err) {
      toast.error(err);
      return;
    }
    if (!url.trim()) {
      toast.error("URL은 필수입니다.");
      return;
    }
    let requestMapping: any = {};
    let responseMapping: any = {};
    try {
      requestMapping = JSON.parse(requestMappingRaw);
    } catch {
      toast.error("Request mapping이 유효한 JSON이 아닙니다.");
      return;
    }
    try {
      responseMapping = JSON.parse(responseMappingRaw);
    } catch {
      toast.error("Response mapping이 유효한 JSON이 아닙니다.");
      return;
    }

    const manifest = {
      ...buildCommonManifest(meta),
      runtime: {
        platform: "webhook",
        method,
        url: url.trim(),
        headers: { "Content-Type": "application/json" },
        auth_ref: authRef.trim() || undefined,
        request_mapping: requestMapping,
        response_mapping: responseMapping,
      },
      output: { type: "text" },
    };

    setSubmitting(true);
    try {
      const created = await agentApi.create({
        slug: meta.slug,
        name: meta.name,
        description: meta.description,
        platform: "webhook",
        capabilities: meta.capabilities,
        manifest,
        visibility: meta.visibility,
        icon: getAutoIcon("webhook"),
        tags: meta.tags ? parseTags(meta.tags) : undefined,
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
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-300">
            <Globe className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">Webhook 등록</h1>
            <p className="text-sm text-muted-foreground">
              외부 REST API (Slack/n8n/Zapier/사내 API) 호출 — 관리자 전용 (Phase 1).
            </p>
          </div>
        </div>

        <div className="space-y-6 rounded-xl border bg-card p-6">
          <section className="space-y-3">
            <h2 className="text-base font-semibold">Webhook 엔드포인트</h2>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="space-y-1.5 md:col-span-1">
                <label className="text-sm font-medium">Method</label>
                <Select value={method} onValueChange={(v) => setMethod(v as any)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="POST">POST</SelectItem>
                    <SelectItem value="GET">GET</SelectItem>
                    <SelectItem value="PUT">PUT</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5 md:col-span-2">
                <label className="text-sm font-medium">URL *</label>
                <Input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://hooks.slack.com/services/T../B../xyz"
                />
                <p className="text-[11px] text-muted-foreground">
                  사설 IP(10.x, 192.168.x, 127.x) 차단됩니다.
                </p>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">자격증명 ref</label>
              <Input
                value={authRef}
                onChange={(e) => setAuthRef(e.target.value)}
                placeholder="ssm:/lucid-hub/webhook/{slug}/auth"
              />
              <p className="text-[11px] text-muted-foreground">
                Hub Vault 참조. 평문 토큰 직접 입력 X.
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">Request Mapping (JSON)</label>
              <Textarea
                value={requestMappingRaw}
                onChange={(e) => setRequestMappingRaw(e.target.value)}
                rows={6}
                className="font-mono text-xs"
              />
              <p className="text-[11px] text-muted-foreground">
                사용자 입력 → request body. 변수는 <code>{`{{var}}`}</code> 템플릿 사용.
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium">Response Mapping (JSON)</label>
              <Textarea
                value={responseMappingRaw}
                onChange={(e) => setResponseMappingRaw(e.target.value)}
                rows={4}
                className="font-mono text-xs"
              />
            </div>
          </section>

          <hr className="border-border" />

          <section className="space-y-3">
            <h2 className="text-base font-semibold">기본 메타 + 분류</h2>
            <CommonMetaSection meta={meta} onChange={setMeta} platform="webhook" />
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
          ⚠ 보안 검증: SSRF · Secret Leak 자동 차단됩니다.
        </p>
      </div>
    </div>
  );
}
