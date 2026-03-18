"use client"

import { Zap, Cpu, TrendingDown } from "lucide-react"
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import { KpiCard } from "./kpi-card"
import { SectionHeader } from "./section-header"
import type { TokenUsageData } from "@/lib/api/report"

interface Props {
  data: TokenUsageData
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

const MODEL_COLORS: Record<string, string> = {
  sonnet: "#3B82F6",
  haiku: "#10B981",
}

const CALLER_COLORS = [
  "#3B82F6", "#10B981", "#F59E0B", "#8B5CF6", "#EF4444",
  "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1",
]

export function TokenUsage({ data }: Props) {
  // 실질 소비 토큰: input + cache_write + output (cache_read = 절감분 제외)
  const effectiveInput = data.totalInputTokens + data.totalCacheWriteTokens
  const totalTokens = effectiveInput + data.totalOutputTokens
  const savedTokens = data.totalCacheReadTokens

  // 워커별 합산 (모델 무관)
  const callerMap = new Map<string, { caller: string; total: number; sonnet: number; haiku: number }>()
  for (const c of data.byCaller) {
    const existing = callerMap.get(c.caller) || { caller: c.caller, total: 0, sonnet: 0, haiku: 0 }
    const tokens = c.inputTokens + c.outputTokens
    existing.total += tokens
    if (c.modelType === "sonnet") existing.sonnet += tokens
    else existing.haiku += tokens
    callerMap.set(c.caller, existing)
  }
  const callerData = Array.from(callerMap.values()).sort((a, b) => b.total - a.total)

  // 모델별 파이차트 데이터
  const modelPieData = data.byModel.map(m => ({
    name: m.modelType === "sonnet" ? "Sonnet" : "Haiku",
    value: m.inputTokens + m.outputTokens,
    color: MODEL_COLORS[m.modelType] || "#9CA3AF",
  }))

  return (
    <section>
      <SectionHeader title="토큰 사용량" subtitle="Token Usage" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
        <KpiCard label="실질 소비 토큰" value={formatTokens(totalTokens)} icon={Zap} accent="blue" />
        <KpiCard label="Input (실질)" value={formatTokens(effectiveInput)} icon={Cpu} accent="green" />
        <KpiCard label="Output 토큰" value={formatTokens(data.totalOutputTokens)} icon={Cpu} accent="orange" />
        <KpiCard label="캐시 절감" value={formatTokens(savedTokens)} icon={TrendingDown} accent="green" />
      </div>

      {/* 모델별 비율 + 일별 추이 */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* 모델별 도넛 */}
        {modelPieData.length > 0 && (
          <div className="rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
            <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">모델별 토큰 비율</h3>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={modelPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {modelPieData.map((entry, idx) => (
                    <Cell key={idx} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #334155", borderRadius: "8px", color: "#F3F4F6" }}
                  formatter={(value) => [formatTokens(Number(value)), "토큰"]}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12 }}
                  formatter={(value) => <span style={{ color: "#F3F4F6" }}>{value}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* 일별 추이 */}
        {data.dailyTrend.length > 0 && (
          <div className="rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
            <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">일별 토큰 추이</h3>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={data.dailyTrend} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} />
                <YAxis tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} tickFormatter={(v) => formatTokens(v)} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #334155", borderRadius: "8px", color: "#F3F4F6" }}
                  formatter={(value, name) => [formatTokens(Number(value)), String(name)]}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: "#9CA3AF" }} />
                <Line type="monotone" dataKey="sonnetTokens" name="Sonnet" stroke="#3B82F6" strokeWidth={2} dot={{ r: 4, fill: "#3B82F6" }} />
                <Line type="monotone" dataKey="haikuTokens" name="Haiku" stroke="#10B981" strokeWidth={2} dot={{ r: 4, fill: "#10B981" }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* 워커별 토큰 사용량 테이블 */}
      <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
        <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">호출자(Worker)별 토큰 사용량</h3>
        <div className="overflow-hidden rounded-lg border border-[#334155]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#334155] bg-[#0F172A]/50">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">호출자</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">Sonnet</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">Haiku</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">합계</th>
              </tr>
            </thead>
            <tbody>
              {callerData.map((c, idx) => (
                <tr key={c.caller} className="border-b border-[#334155]/50 transition-colors hover:bg-[#334155]/20">
                  <td className="px-4 py-2.5 font-mono text-[#F3F4F6]">
                    <span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: CALLER_COLORS[idx % CALLER_COLORS.length] }} />
                    {c.caller}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-[#3B82F6]">{c.sonnet > 0 ? formatTokens(c.sonnet) : "-"}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-[#10B981]">{c.haiku > 0 ? formatTokens(c.haiku) : "-"}</td>
                  <td className="px-4 py-2.5 text-right font-mono font-medium text-[#F3F4F6]">{formatTokens(c.total)}</td>
                </tr>
              ))}
              {callerData.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-[#9CA3AF]">해당 기간에 토큰 사용 데이터가 없습니다</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
