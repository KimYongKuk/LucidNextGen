"use client"

import { MessageSquare, Users, TrendingUp } from "lucide-react"
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
import type { OverviewData } from "@/lib/api/report"

interface Props {
  data: OverviewData
}

export function UsageOverview({ data }: Props) {
  return (
    <section>
      <SectionHeader title="사용 현황" subtitle="Usage Overview" />

      <div className="grid grid-cols-3 gap-4">
        <KpiCard label="총 메시지 수" value={data.total_messages.toLocaleString()} icon={MessageSquare} accent="blue" />
        <KpiCard label="총 세션 수" value={data.total_sessions} icon={TrendingUp} accent="green" />
        <KpiCard label="활성 사용자 수" value={data.active_users} icon={Users} accent="orange" />
      </div>

      <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
        <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">일별 메시지 / 세션 / 사용자 추이</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data.daily_trend} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} />
            <YAxis tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #334155", borderRadius: "8px", color: "#F3F4F6" }}
              labelStyle={{ color: "#9CA3AF" }}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "#9CA3AF" }} />
            <Line type="monotone" dataKey="messages" name="메시지" stroke="#3B82F6" strokeWidth={2} dot={{ r: 4, fill: "#3B82F6" }} activeDot={{ r: 6 }} />
            <Line type="monotone" dataKey="sessions" name="세션" stroke="#10B981" strokeWidth={2} dot={{ r: 4, fill: "#10B981" }} activeDot={{ r: 6 }} />
            <Line type="monotone" dataKey="users" name="사용자" stroke="#F59E0B" strokeWidth={2} dot={{ r: 4, fill: "#F59E0B" }} activeDot={{ r: 6 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
