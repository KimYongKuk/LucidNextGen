"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, Bot, Eye, EyeOff, KeyRound, ExternalLink, Loader2, Plus, Trash2 } from "lucide-react";
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
import { useDebounce } from "@/hooks/use-debounce";

const MISO_FACTORY_URL = process.env.NEXT_PUBLIC_MISO_FACTORY_URL || "https://factory.miso.landf.co.kr";

export default function NewMisoAgentPage() {
  const router = useRouter();
  const [meta, setMeta] = useState<CommonMeta>(DEFAULT_META);
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  // 워크플로우 입력 변수 매핑 — multi-row, type-aware (Workflow 모드 전용)
  type WfInputType = "text" | "paragraph" | "list" | "number" | "file" | "files";
  type WfInputRow = { name: string; type: WfInputType; source: string };
  const [workflowInputs, setWorkflowInputs] = useState<WfInputRow[]>([]);

  const addWorkflowInput = () => {
    setWorkflowInputs((rows) => [...rows, { name: "", type: "text", source: "{{message}}" }]);
  };
  const removeWorkflowInput = (idx: number) => {
    setWorkflowInputs((rows) => rows.filter((_, i) => i !== idx));
  };
  const updateWorkflowInput = (idx: number, patch: Partial<WfInputRow>) => {
    setWorkflowInputs((rows) =>
      rows.map((r, i) => {
        if (i !== idx) return r;
        const merged = { ...r, ...patch };
        // 타입 변경 시 source 기본값 자동 보정 (사용자가 직접 입력했으면 그대로)
        if (patch.type && !patch.source) {
          if (patch.type === "list") merged.source = "{{message_lines}}";
          else if (patch.type === "number") merged.source = "{{message_number}}";
          else if (patch.type === "file") merged.source = "{{latest_file}}";
          else if (patch.type === "files") merged.source = "{{recent_files}}";
          else merged.source = "{{message}}";
        }
        return merged;
      })
    );
  };

  // type별 기본 source 옵션 (드롭다운 선택지). 고정값은 free-text input으로 별도 처리.
  const sourceOptionsForType = (t: WfInputType): { value: string; label: string }[] => {
    if (t === "text" || t === "paragraph") {
      return [{ value: "{{message}}", label: "사용자 발화 그대로" }];
    }
    if (t === "list") {
      return [
        { value: "{{message_lines}}", label: "사용자 발화를 줄바꿈 단위로 분리" },
        { value: "{{message}}", label: "사용자 발화 1개를 항목으로" },
      ];
    }
    if (t === "number") {
      return [{ value: "{{message_number}}", label: "사용자 발화에서 첫 숫자 추출" }];
    }
    if (t === "file") {
      return [
        { value: "{{latest_file}}", label: "[채팅 첨부] 가장 최근 업로드한 파일 1개" },
      ];
    }
    if (t === "files") {
      return [
        { value: "{{recent_files}}", label: "[채팅 첨부] 최근 10분 내 첨부한 파일 모두" },
        { value: "{{recent_files:3}}", label: "[채팅 첨부] 가장 최근 3개" },
        { value: "{{recent_files:5}}", label: "[채팅 첨부] 가장 최근 5개" },
        { value: "{{recent_files:10}}", label: "[채팅 첨부] 가장 최근 10개" },
        { value: "{{workspace_files}}", label: "[워크스페이스] 영속 파일 모두" },
        { value: "{{workspace_files:3}}", label: "[워크스페이스] 영속 파일 최근 3개" },
        { value: "{{workspace_files:5}}", label: "[워크스페이스] 영속 파일 최근 5개" },
        { value: "{{workspace_files:10}}", label: "[워크스페이스] 영속 파일 최근 10개" },
      ];
    }
    return [{ value: "{{message}}", label: "사용자 발화" }];
  };
  // 캡처 이미지 — 첫 시도 후 없으면 영구 숨김 (반복 404 방지). SSR과 CSR 일치를 위해 useEffect로 마운트 후 sessionStorage 확인
  const [imageVisible, setImageVisible] = useState<boolean>(true);
  useEffect(() => {
    try {
      if (sessionStorage.getItem("miso-help-img-missing") === "1") {
        setImageVisible(false);
      }
    } catch {}
  }, []);
  const [submitting, setSubmitting] = useState(false);
  const [verifyState, setVerifyState] = useState<
    | { kind: "idle" }
    | { kind: "verifying" }
    | { kind: "valid"; mode: "chat" | "workflow" }
    | { kind: "invalid"; reason: string }
  >({ kind: "idle" });

  const keyFormatOk = apiKey.startsWith("app-") && apiKey.length >= 20;
  const debouncedKey = useDebounce(apiKey, 600);

  // 키 입력 안정화 시 실시간 검증 (백엔드에 시험 호출)
  useEffect(() => {
    if (!debouncedKey || !debouncedKey.startsWith("app-") || debouncedKey.length < 20) {
      setVerifyState({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setVerifyState({ kind: "verifying" });
    (async () => {
      try {
        const result = await agentApi.probeMiso(debouncedKey);
        if (cancelled) return;
        if (result.valid && result.mode) {
          setVerifyState({ kind: "valid", mode: result.mode });
        } else {
          setVerifyState({ kind: "invalid", reason: result.reason ?? "유효하지 않은 키" });
        }
      } catch (e: any) {
        if (cancelled) return;
        setVerifyState({ kind: "invalid", reason: e?.message ?? "검증 실패" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [debouncedKey]);

  const handleSubmit = async () => {
    const err = validateCommon(meta);
    if (err) {
      toast.error(err);
      return;
    }
    if (!keyFormatOk) {
      toast.error("MISO API 키를 정확히 입력하세요. (app-... 형식, 20자 이상)");
      return;
    }
    if (verifyState.kind !== "valid") {
      toast.error("MISO API 키 검증이 통과되지 않았습니다. 키를 다시 확인해주세요.");
      return;
    }

    // 유형(mode)/endpoint는 백엔드가 등록 시점에 자동 판별하여 매니페스트에 채움.
    const runtime: Record<string, any> = {
      platform: "miso",
      api_key: apiKey,
    };
    // Workflow 모드 + 입력 변수 매핑이 1행 이상이면 list 형태로 주입.
    // 비워두면 백엔드가 best-effort(흔한 6개 변수명에 사용자 발화 매핑)로 시도.
    if (verifyState.kind === "valid" && verifyState.mode === "workflow") {
      const validRows = workflowInputs
        .map((r) => ({ name: r.name.trim(), type: r.type, source: r.source.trim() }))
        .filter((r) => r.name);
      // 변수명 중복 검증
      const nameSet = new Set<string>();
      for (const r of validRows) {
        if (nameSet.has(r.name)) {
          toast.error(`변수명 '${r.name}'이 중복되었습니다.`);
          return;
        }
        nameSet.add(r.name);
      }
      if (validRows.length > 0) {
        runtime.input_mapping = validRows;
      }
    }
    const manifest = {
      ...buildCommonManifest(meta),
      runtime,
      output: { type: "text" },
    };

    setSubmitting(true);
    try {
      const created = await agentApi.create({
        slug: meta.slug,
        name: meta.name,
        description: meta.description,
        platform: "miso",
        capabilities: meta.capabilities,
        manifest,
        visibility: meta.visibility,
        icon: getAutoIcon("miso"),
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
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-300">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">MISO Agent / Workflow 등록</h1>
            <p className="text-sm text-muted-foreground">
              MISO 빌더에서 만든 Agent/Workflow를 카탈로그에 연결합니다.
            </p>
          </div>
        </div>

        <div className="space-y-6 rounded-xl border bg-card p-6">
          {/* 1. MISO 연결 */}
          <section className="space-y-4">
            <h2 className="text-base font-semibold">1. MISO와 연결</h2>

            {/* API 키 발급 안내 박스 */}
            <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4 dark:border-blue-900 dark:bg-blue-950/30">
              <div className="flex items-start gap-2">
                <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />
                <div className="flex-1 text-xs">
                  <p className="font-semibold text-blue-900 dark:text-blue-200">
                    MISO API 키 발급 방법
                  </p>
                  <ol className="mt-2 ml-4 list-decimal space-y-0.5 text-blue-900/80 dark:text-blue-200/80">
                    <li>MISO Factory에서 등록할 앱 선택</li>
                    <li>우측 상단 <b>"앱 공유하기"</b> 클릭</li>
                    <li><b>"다른 서비스와 연결하기"</b> 탭 진입</li>
                    <li><b>"API 키 생성"</b> 버튼 → 생성된 키 복사 (<code className="font-mono">app-...</code>)</li>
                  </ol>
                  <a
                    href={MISO_FACTORY_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-blue-700 hover:underline dark:text-blue-300"
                  >
                    <ExternalLink className="h-3 w-3" />
                    MISO Factory 열기
                  </a>
                </div>
              </div>
              {imageVisible && (
                <div className="mt-3 overflow-hidden rounded-md border border-blue-200 dark:border-blue-900">
                  {/* 캡처 이미지 (없으면 숨김) */}
                  <Image
                    src="/help/miso-api-key-issue.png"
                    alt="MISO API 키 발급 화면"
                    width={1872}
                    height={290}
                    className="h-auto w-full"
                    onError={() => {
                      setImageVisible(false);
                      try {
                        sessionStorage.setItem("miso-help-img-missing", "1");
                      } catch {}
                    }}
                    unoptimized
                  />
                </div>
              )}
            </div>

            {/* API 키 입력 */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium">MISO API 키 *</label>
              <div className="relative">
                <Input
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value.trim())}
                  placeholder="app-..."
                  className="pr-10 font-mono text-xs"
                  autoComplete="off"
                  spellCheck={false}
                />
                <button
                  type="button"
                  onClick={() => setShowKey((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-muted"
                  tabIndex={-1}
                >
                  {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {apiKey && !keyFormatOk && (
                <p className="text-[11px] text-amber-600 dark:text-amber-400">
                  ⚠ MISO API 키는 <code className="font-mono">app-</code>로 시작합니다.
                </p>
              )}
              {keyFormatOk && verifyState.kind === "verifying" && (
                <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  MISO 서버에 키 검증 중...
                </p>
              )}
              {verifyState.kind === "valid" && (
                <p className="text-[11px] text-emerald-600 dark:text-emerald-400">
                  ✓ 유효한 MISO 키 — 유형 자동 인식: <b>{verifyState.mode === "chat" ? "Chat" : "Workflow"}</b>
                </p>
              )}
              {verifyState.kind === "invalid" && keyFormatOk && (
                <p className="text-[11px] text-red-600 dark:text-red-400">
                  ✗ {verifyState.reason}
                </p>
              )}
            </div>

            {/* Chat/Workflow 자동 결정 안내 */}
            <p className="text-[11px] text-muted-foreground">
              ℹ Chat/Workflow 유형은 등록 시 API 키로 <b>자동 판별</b>됩니다.
            </p>

            {/* Workflow 모드 — 입력 변수 매핑 (multi-row, type-aware) */}
            {verifyState.kind === "valid" && verifyState.mode === "workflow" && (
              <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-900 dark:bg-amber-950/30">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-amber-900 dark:text-amber-200">
                    워크플로우 입력 변수 매핑 <span className="text-muted-foreground">(권장)</span>
                  </label>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={addWorkflowInput}
                    className="h-7 px-2 text-xs"
                  >
                    <Plus className="mr-1 h-3 w-3" />
                    변수 추가
                  </Button>
                </div>

                <p className="text-[11px] text-amber-900/80 dark:text-amber-200/80">
                  MISO Studio에서 정의한 워크플로우의 <b>시작 노드 입력 변수</b>를 그대로 등록하세요.
                  변수명·타입·매핑 소스를 행 단위로 추가합니다.
                </p>

                {workflowInputs.length === 0 ? (
                  <p className="rounded border border-dashed border-amber-300 bg-background/40 px-3 py-3 text-center text-[11px] text-muted-foreground dark:border-amber-800">
                    변수가 없으면 빈 inputs로 호출됩니다. (워크플로우가 입력 없이 동작하는 경우만)
                  </p>
                ) : (
                  <div className="space-y-2">
                    {workflowInputs.map((row, idx) => {
                      const sourceOpts = sourceOptionsForType(row.type);
                      return (
                        <div
                          key={idx}
                          className="grid grid-cols-[1fr_120px_1fr_32px] gap-2 rounded-md border bg-background p-2 dark:bg-background"
                        >
                          {/* 변수명 */}
                          <Input
                            type="text"
                            value={row.name}
                            onChange={(e) => updateWorkflowInput(idx, { name: e.target.value })}
                            placeholder="변수명 (예: user_query)"
                            className="h-8 font-mono text-xs"
                            autoComplete="off"
                            spellCheck={false}
                          />
                          {/* 타입 */}
                          <Select
                            value={row.type}
                            onValueChange={(v) =>
                              updateWorkflowInput(idx, { type: v as WfInputType, source: "" })
                            }
                          >
                            <SelectTrigger className="h-8 text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="text">텍스트</SelectItem>
                              <SelectItem value="paragraph">문단</SelectItem>
                              <SelectItem value="list">목록</SelectItem>
                              <SelectItem value="number">숫자</SelectItem>
                              <SelectItem value="file">단일 파일</SelectItem>
                              <SelectItem value="files">다중 파일</SelectItem>
                            </SelectContent>
                          </Select>
                          {/* 소스 */}
                          <Select
                            value={row.source}
                            onValueChange={(v) => updateWorkflowInput(idx, { source: v })}
                          >
                            <SelectTrigger className="h-8 text-xs">
                              <SelectValue placeholder="매핑 소스" />
                            </SelectTrigger>
                            <SelectContent>
                              {sourceOpts.map((opt) => (
                                <SelectItem key={opt.value} value={opt.value}>
                                  {opt.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          {/* 삭제 */}
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            onClick={() => removeWorkflowInput(idx)}
                            className="h-8 w-8 text-muted-foreground hover:text-red-600"
                            aria-label="삭제"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="rounded-md bg-amber-100/50 p-2 text-[11px] text-amber-900 dark:bg-amber-950/50 dark:text-amber-200/90">
                  <p className="font-semibold">📎 파일 변수 사용 안내</p>
                  <ul className="mt-0.5 ml-4 list-disc space-y-0.5">
                    <li>
                      <b>[채팅 첨부]</b> 출처: 사용자가 호출 직전 채팅창에 첨부한 일회성 파일.
                      매번 다른 파일로 호출할 때 적합 (사용자 직접 요청 케이스).
                    </li>
                    <li>
                      <b>[워크스페이스]</b> 출처: 워크스페이스에 영속 보관된 파일.
                      매번 같은 파일로 호출할 때 적합 (cron 자동 호출 / 정기 분석 케이스).
                    </li>
                    <li>
                      두 출처는 토큰으로 명확히 분리되어 사용자가 다르게 행동해도 항상 의도대로 매핑됩니다.
                      한 호출 최대 10개. 출처에 파일이 없으면 친절한 에러로 안내.
                    </li>
                  </ul>
                </div>
              </div>
            )}
          </section>

          <hr className="border-border" />

          {/* 2. 기본 정보 */}
          <section className="space-y-3">
            <h2 className="text-base font-semibold">2. 기본 정보</h2>
            <CommonMetaSection meta={meta} onChange={setMeta} platform="miso" />
          </section>

          <hr className="border-border" />

          <div className="flex justify-end gap-2">
            <Button asChild variant="ghost">
              <Link href="/agent-store/new">취소</Link>
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={submitting || verifyState.kind !== "valid"}
              title={verifyState.kind !== "valid" ? "MISO 키 검증이 통과되어야 등록 가능" : undefined}
            >
              {submitting ? "등록 중..." : "등록하기"}
            </Button>
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground">
          등록 후 자동 검증 → 관리자 승인 → 카탈로그 노출 흐름으로 진행됩니다.
        </p>
      </div>
    </div>
  );
}
