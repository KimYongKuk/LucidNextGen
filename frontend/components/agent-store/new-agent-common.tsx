"use client";

import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronRight, Pencil } from "lucide-react";
import type { AgentCapability, AgentVisibility, AgentPlatform } from "@/lib/api/agents";

// ============================================================
// 공통 메타 상태
// ============================================================
export type CommonMeta = {
  slug: string;             // 자동 생성, 고급에서 수정 가능
  slugTouched: boolean;     // 사용자가 직접 수정한 적 있는지
  name: string;
  description: string;
  tags: string;
  visibility: AgentVisibility;
  capabilities: AgentCapability[];
  systemPrompt: string;
  schedulePreset: SchedulePreset;
  scheduleHour: number;     // 매일/매주/매월 공통 시간
  scheduleMinute: number;
  scheduleWeekday: number;  // 매주 (0=일~6=토)
  scheduleDay: number;      // 매월 (1~31)
  customCron: string;       // 고급
  // 스케줄 자동 실행 시 워크플로우/Agent에 보낼 프롬프트.
  // 비워두면 백엔드 default("🔄 자동 실행: 정기 워크플로우를 실행해주세요.") 사용.
  schedulePrompt: string;
};

export type SchedulePreset =
  | "none"
  | "daily"
  | "weekly"
  | "monthly"
  | "custom";

export const DEFAULT_META: CommonMeta = {
  slug: "",
  slugTouched: false,
  name: "",
  description: "",
  tags: "",
  visibility: "private",
  capabilities: ["chat"],
  systemPrompt: "",
  schedulePreset: "none",
  scheduleHour: 9,
  scheduleMinute: 0,
  scheduleWeekday: 1,
  scheduleDay: 1,
  customCron: "",
  schedulePrompt: "",
};

// ============================================================
// Capability 옵션 + 충돌 검사
// ============================================================
const CAPABILITY_OPTIONS: { value: AgentCapability; label: string; hint: string }[] = [
  { value: "chat", label: "💬 대화형", hint: "사용자가 자연어로 질문" },
  { value: "run", label: "⚡ 실행형", hint: "폼 입력 후 실행" },
  { value: "scheduled", label: "📅 스케줄", hint: "정해진 시각에 자동 실행" },
  { value: "async", label: "⏳ 비동기", hint: "실행 후 완료되면 알림" },
];

// chat과 run은 상호 배타 (사용자 발화 시 라우팅 모호)
const MUTEX_PAIRS: [AgentCapability, AgentCapability][] = [
  ["chat", "run"],
];

function getMutexConflict(selected: AgentCapability[]): AgentCapability[] {
  for (const [a, b] of MUTEX_PAIRS) {
    if (selected.includes(a) && selected.includes(b)) return [a, b];
  }
  return [];
}

// ============================================================
// Slug 자동 생성 (이름 → 영문 slug)
// ============================================================
function generateSlug(name: string): string {
  // 한글 제거 → 영문/숫자만 keep + 공백을 -로
  const ascii = name
    .toLowerCase()
    .replace(/[^ -~]/g, "") // ASCII만
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  if (ascii.length >= 2) return ascii.slice(0, 80);
  // 한글 이름 → 임의 짧은 hash 기반 slug
  return `agent-${Date.now().toString(36).slice(-6)}`;
}

// ============================================================
// Cron 빌더
// ============================================================
const WEEKDAY_LABELS = ["일", "월", "화", "수", "목", "금", "토"];

export function buildCron(meta: CommonMeta): string {
  const { schedulePreset, scheduleHour, scheduleMinute, scheduleWeekday, scheduleDay, customCron } = meta;
  if (schedulePreset === "none") return "";
  if (schedulePreset === "custom") return customCron.trim();
  if (schedulePreset === "daily") return `${scheduleMinute} ${scheduleHour} * * *`;
  if (schedulePreset === "weekly") return `${scheduleMinute} ${scheduleHour} * * ${scheduleWeekday}`;
  if (schedulePreset === "monthly") return `${scheduleMinute} ${scheduleHour} ${scheduleDay} * *`;
  return "";
}

// ============================================================
// 컴포넌트
// ============================================================
interface Props {
  meta: CommonMeta;
  onChange: (next: CommonMeta) => void;
  platform: AgentPlatform;
}

export function CommonMetaSection({ meta, onChange, platform }: Props) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [editSlug, setEditSlug] = useState(false);

  // 이름 변경 시 slug 자동 갱신 (사용자가 수동 수정 안 한 경우)
  useEffect(() => {
    if (!meta.slugTouched && meta.name) {
      const auto = generateSlug(meta.name);
      if (auto && auto !== meta.slug) {
        onChange({ ...meta, slug: auto });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta.name]);

  const set = <K extends keyof CommonMeta>(key: K, value: CommonMeta[K]) =>
    onChange({ ...meta, [key]: value });

  const toggleCapability = (cap: AgentCapability) => {
    const next = meta.capabilities.includes(cap)
      ? meta.capabilities.filter((c) => c !== cap)
      : [...meta.capabilities, cap];
    onChange({ ...meta, capabilities: next });
  };

  const conflict = getMutexConflict(meta.capabilities);

  return (
    <div className="space-y-4">
      {/* 이름 */}
      <Field label="이름 *">
        <Input
          value={meta.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder="월간 매출 리포트"
        />
        {meta.name && meta.slug && !editSlug && (
          <p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
            <span>주소(자동): /agent-store/<code className="font-mono">{meta.slug}</code></span>
            <button
              type="button"
              onClick={() => setEditSlug(true)}
              className="inline-flex items-center text-primary hover:underline"
            >
              <Pencil className="ml-1 h-3 w-3" /> 수정
            </button>
          </p>
        )}
      </Field>

      {/* 슬러그 (수정 모드) */}
      {editSlug && (
        <Field label="주소 (URL 식별자)" hint="소문자/숫자/하이픈, 2~80자">
          <Input
            value={meta.slug}
            onChange={(e) => onChange({ ...meta, slug: e.target.value, slugTouched: true })}
            placeholder="monthly-sales-report"
          />
        </Field>
      )}

      {/* 설명 */}
      <Field label="설명 *" hint="이 Agent가 무엇을 하는지 한 문장">
        <Textarea
          value={meta.description}
          onChange={(e) => set("description", e.target.value)}
          rows={2}
          placeholder="ERP 매출 데이터를 추출하여 엑셀 보고서를 자동 생성합니다."
        />
      </Field>

      {/* 태그 + 공개범위 */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field label="태그 (쉼표 구분)">
          <Input
            value={meta.tags}
            onChange={(e) => set("tags", e.target.value)}
            placeholder="매출, 보고서, ERP"
          />
        </Field>
        <Field label="공개 범위 *">
          <Select value={meta.visibility} onValueChange={(v) => set("visibility", v as AgentVisibility)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="private">Private (나만)</SelectItem>
              <SelectItem value="team">Team (우리 팀)</SelectItem>
              <SelectItem value="public">Public (전사 공개)</SelectItem>
            </SelectContent>
          </Select>
        </Field>
      </div>

      {/* Capabilities */}
      <Field label="이 Agent의 사용 방식 * (다중 선택 가능)">
        <div className="flex flex-wrap gap-2">
          {CAPABILITY_OPTIONS.map((opt) => {
            const active = meta.capabilities.includes(opt.value);
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => toggleCapability(opt.value)}
                title={opt.hint}
                className={[
                  "rounded-full border px-3 py-1.5 text-xs transition-colors",
                  active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input bg-background text-foreground hover:bg-muted",
                ].join(" ")}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        {conflict.length > 0 && (
          <p className="mt-1.5 text-[11px] text-red-600 dark:text-red-400">
            ⚠ <b>{conflict.join(" + ")}</b>는 함께 선택할 수 없습니다 (라우팅이 모호해짐). 하나만 선택하세요.
          </p>
        )}
      </Field>

      {/* 시스템 프롬프트 — 라우팅 안내용 */}
      <Field
        label="라우팅 안내 (Hub 시스템 프롬프트)"
        hint="이 Agent를 언제 호출할지 Hub LLM에 알려주는 안내문. 짧고 명확하게."
      >
        <Textarea
          value={meta.systemPrompt}
          onChange={(e) => set("systemPrompt", e.target.value)}
          rows={3}
          placeholder="사용자가 매출 분석을 요청하면 이 Agent를 호출하세요. 결과는 표/차트로 정리합니다."
        />
        <div className="mt-1 rounded-md border border-amber-200/60 bg-amber-50/40 p-2 text-[11px] text-amber-900/80 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200/80">
          <p>
            <b>이 필드는 "언제 호출할지" 라우팅 안내용입니다.</b>
          </p>
          <p className="mt-1">
            ✅ <b>적는 것</b>: 트리거 발화 패턴, 결과 형식 가이드, 다른 Agent와의 구분 기준
          </p>
          <p>
            ❌ <b>적지 말 것</b>: Agent 자체의 페르소나/응답 스타일 (그건 MISO Studio / 매크로 코드 안에서 설정)
          </p>
        </div>
      </Field>

      {/* 자동 실행 */}
      <Field label="자동 실행">
        <div className="space-y-2">
          <Select value={meta.schedulePreset} onValueChange={(v) => set("schedulePreset", v as SchedulePreset)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">실행 안 함 (사용자 호출만)</SelectItem>
              <SelectItem value="daily">매일</SelectItem>
              <SelectItem value="weekly">매주</SelectItem>
              <SelectItem value="monthly">매월</SelectItem>
              <SelectItem value="custom">고급 — cron 직접 입력</SelectItem>
            </SelectContent>
          </Select>

          {meta.schedulePreset === "daily" && (
            <TimeInput meta={meta} onChange={onChange} />
          )}
          {meta.schedulePreset === "weekly" && (
            <div className="flex flex-wrap gap-2">
              {WEEKDAY_LABELS.map((w, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => set("scheduleWeekday", i)}
                  className={[
                    "rounded-md border px-2.5 py-1 text-xs",
                    meta.scheduleWeekday === i
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input bg-background hover:bg-muted",
                  ].join(" ")}
                >
                  {w}요일
                </button>
              ))}
              <TimeInput meta={meta} onChange={onChange} />
            </div>
          )}
          {meta.schedulePreset === "monthly" && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs">매월</span>
              <Input
                type="number"
                min={1}
                max={31}
                value={meta.scheduleDay}
                onChange={(e) => set("scheduleDay", parseInt(e.target.value || "1", 10))}
                className="w-20"
              />
              <span className="text-xs">일</span>
              <TimeInput meta={meta} onChange={onChange} />
            </div>
          )}
          {meta.schedulePreset === "custom" && (
            <Input
              value={meta.customCron}
              onChange={(e) => set("customCron", e.target.value)}
              placeholder="0 9 1 * * (매월 1일 09시)"
              className="font-mono text-xs"
            />
          )}

          {meta.schedulePreset !== "none" && (
            <>
              <p className="text-[11px] text-muted-foreground">
                현재 cron: <code className="font-mono">{buildCron(meta) || "(미설정)"}</code>
              </p>

              {/* 분단위 cron 경고 */}
              {(() => {
                const c = buildCron(meta);
                const isMinuteLevel = c && /^\*\/?\d+ /.test(c) && c.startsWith("*");
                if (!isMinuteLevel) return null;
                return (
                  <p className="rounded bg-orange-50 px-2 py-1.5 text-[11px] text-orange-900 dark:bg-orange-950/40 dark:text-orange-200">
                    ⚠ 분단위 자동 실행은 채팅 세션이 빠르게 늘어납니다. 정말 필요한 경우만 사용하세요.
                  </p>
                );
              })()}

              {/* 자동 실행 시 보낼 프롬프트 */}
              <div className="space-y-1.5 rounded-lg border border-blue-200 bg-blue-50/50 p-3 dark:border-blue-900 dark:bg-blue-950/30">
                <label className="text-xs font-medium text-blue-900 dark:text-blue-200">
                  자동 실행 시 보낼 프롬프트 <span className="text-muted-foreground">(선택)</span>
                </label>
                <Input
                  type="text"
                  value={meta.schedulePrompt}
                  onChange={(e) => set("schedulePrompt", e.target.value)}
                  placeholder="예: 어제 매출 데이터를 분석하여 인사이트 리포트를 작성해주세요."
                  className="text-xs bg-background"
                />
                <p className="text-[11px] text-blue-900/80 dark:text-blue-200/80">
                  스케줄러가 자동 호출 시 워크플로우/Agent에 보낼 사용자 발화입니다.
                  비워두면 default("🔄 자동 실행")가 사용됩니다. 워크플로우에 명확히 무엇을 해야 할지 적어주세요.
                </p>
              </div>
            </>
          )}
        </div>
      </Field>
    </div>
  );
}

function TimeInput({ meta, onChange }: { meta: CommonMeta; onChange: (m: CommonMeta) => void }) {
  return (
    <div className="flex items-center gap-1">
      <Input
        type="number"
        min={0}
        max={23}
        value={meta.scheduleHour}
        onChange={(e) =>
          onChange({ ...meta, scheduleHour: Math.min(23, Math.max(0, parseInt(e.target.value || "0", 10))) })
        }
        className="w-16"
      />
      <span className="text-xs">시</span>
      <Input
        type="number"
        min={0}
        max={59}
        value={meta.scheduleMinute}
        onChange={(e) =>
          onChange({ ...meta, scheduleMinute: Math.min(59, Math.max(0, parseInt(e.target.value || "0", 10))) })
        }
        className="w-16"
      />
      <span className="text-xs">분</span>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

// ============================================================
// 매니페스트 빌더 + 검증
// ============================================================

// 플랫폼별 자동 아이콘
const PLATFORM_ICONS: Record<AgentPlatform, string> = {
  native: "💬",
  miso: "🤖",
  runner: "⚙️",
  webhook: "🌐",
};

export function getAutoIcon(platform: AgentPlatform): string {
  return PLATFORM_ICONS[platform];
}

export function buildCommonManifest(meta: CommonMeta) {
  const manifest: any = {
    intent_hints: meta.systemPrompt
      ? { system_prompt: meta.systemPrompt }
      : undefined,
    inputs: [],
    requires: { connectors: [], permissions: [] },
  };
  const cron = buildCron(meta);
  if (cron) {
    const trigger: Record<string, any> = { type: "schedule", cron, timezone: "Asia/Seoul" };
    const prompt = (meta.schedulePrompt || "").trim();
    if (prompt) trigger.prompt = prompt;
    manifest.triggers = [trigger];
  }
  return manifest;
}

export function parseTags(input: string): string[] {
  return input
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

export function validateCommon(meta: CommonMeta): string | null {
  if (!meta.name.trim()) return "이름은 필수입니다.";
  if (!/^[a-z0-9-]{2,80}$/.test(meta.slug)) {
    return "주소(slug)가 유효하지 않습니다 — 영문 소문자/숫자/하이픈 2~80자.";
  }
  if (!meta.description.trim()) return "설명은 필수입니다.";
  if (meta.capabilities.length === 0) return "사용 방식은 최소 1개 이상 선택하세요.";
  const conflict = getMutexConflict(meta.capabilities);
  if (conflict.length > 0) {
    return `'${conflict.join(" + ")}'는 함께 선택할 수 없습니다.`;
  }
  if (meta.schedulePreset === "custom" && !meta.customCron.trim()) {
    return "고급 cron 표현식을 입력하거나 다른 자동 실행 옵션을 선택하세요.";
  }
  return null;
}
