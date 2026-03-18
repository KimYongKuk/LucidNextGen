"use client"

import { MessageSquare, Users, TrendingUp, Zap } from "lucide-react"
import {
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
import type { OverviewData, TokenUsageData } from "@/lib/api/report"

interface Props {
  data: OverviewData
  tokenData?: TokenUsageData
}

function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

export function UsageOverview({ data, tokenData }: Props) {
  // 실질 소비 토큰: input + cache_write + output (cache_read = 절감분 제외)
  const totalTokens = tokenData
    ? tokenData.totalInputTokens + tokenData.totalCacheWriteTokens + tokenData.totalOutputTokens
    : 0

  // 트렌드 차트 데이터: 메시지/세션/사용자 + 토큰(K)
  const trendData = data.daily_trend.map((d) => {
    const tokenEntry = tokenData?.dailyTrend.find((t) => t.date === d.date)
    const tokenK = tokenEntry
      ? Math.round((tokenEntry.sonnetTokens + tokenEntry.haikuTokens) / 1000)
      : 0
    return { ...d, tokenK }
  })

  const hasTokenTrend = trendData.some((d) => d.tokenK > 0)

  return (
    <section>
      <SectionHeader title="사용 현황" subtitle="Usage Overview" />

      <div className="grid grid-cols-4 gap-4">
        <KpiCard label="총 메시지 수" value={data.total_messages.toLocaleString()} icon={MessageSquare} accent="blue" />
        <KpiCard label="총 세션 수" value={data.total_sessions} icon={TrendingUp} accent="green" />
        <KpiCard label="활성 사용자 수" value={data.active_users} icon={Users} accent="orange" />
        <KpiCard label="총 토큰 사용량" value={formatTokenCount(totalTokens)} icon={Zap} accent="purple" />
      </div>

      <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
        <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">일별 메시지 / 세션 / 사용자 / 토큰 추이</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={trendData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} />
            <YAxis yAxisId="left" tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} />
            {hasTokenTrend && (
              <YAxis yAxisId="right" orientation="right" tick={{ fill: "#8B5CF6", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} unit="K" />
            )}
            <Tooltip
              contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #334155", borderRadius: "8px", color: "#F3F4F6" }}
              labelStyle={{ color: "#9CA3AF" }}
              formatter={(value, name) =>
                name === "토큰" ? [`${Number(value).toLocaleString()}K`, name] : [Number(value).toLocaleString(), name]
              }
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "#9CA3AF" }} />
            <Line yAxisId="left" type="monotone" dataKey="messages" name="메시지" stroke="#3B82F6" strokeWidth={2} dot={{ r: 4, fill: "#3B82F6" }} activeDot={{ r: 6 }} />
            <Line yAxisId="left" type="monotone" dataKey="sessions" name="세션" stroke="#10B981" strokeWidth={2} dot={{ r: 4, fill: "#10B981" }} activeDot={{ r: 6 }} />
            <Line yAxisId="left" type="monotone" dataKey="users" name="사용자" stroke="#F59E0B" strokeWidth={2} dot={{ r: 4, fill: "#F59E0B" }} activeDot={{ r: 6 }} />
            {hasTokenTrend && (
              <Line yAxisId="right" type="monotone" dataKey="tokenK" name="토큰" stroke="#8B5CF6" strokeWidth={2} strokeDasharray="5 3" dot={{ r: 4, fill: "#8B5CF6" }} activeDot={{ r: 6 }} />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
