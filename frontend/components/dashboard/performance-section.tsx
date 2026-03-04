"use client"

import { Clock, Gauge } from "lucide-react"
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
import type { PerformanceData } from "@/lib/api/report"

interface Props {
  data: PerformanceData
}

export function PerformanceSection({ data }: Props) {
  const avgSec = (data.avgResponseMs / 1000).toFixed(1)
  const p95Sec = (data.p95ResponseMs / 1000).toFixed(1)

  return (
    <section>
      <SectionHeader title="성능" subtitle="Performance" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <KpiCard label="평균 응답시간" value={`${avgSec}초`} icon={Clock} accent="blue" />
        <KpiCard label="P95 응답시간" value={`${p95Sec}초`} icon={Gauge} accent="orange" />
      </div>

      <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
        <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">일별 평균 / P95 응답시간 추이 (초)</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data.dailyTrend} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} />
            <YAxis tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} unit="s" />
            <Tooltip
              contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #334155", borderRadius: "8px", color: "#F3F4F6" }}
              formatter={(value) => [`${value}초`]}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "#9CA3AF" }} />
            <Line type="monotone" dataKey="avgResponse" name="평균" stroke="#3B82F6" strokeWidth={2} dot={{ r: 4, fill: "#3B82F6" }} activeDot={{ r: 6 }} />
            <Line type="monotone" dataKey="p95Response" name="P95" stroke="#F59E0B" strokeWidth={2} dot={{ r: 4, fill: "#F59E0B" }} activeDot={{ r: 6 }} strokeDasharray="5 5" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
        <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">워커별 성능</h3>
        <div className="overflow-hidden rounded-lg border border-[#334155]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#334155] bg-[#0F172A]/50">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">워커명</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">평균 (ms)</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">P95 (ms)</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">처리 건수</th>
              </tr>
            </thead>
            <tbody>
              {data.byWorker.map((w) => (
                <tr key={w.worker} className="border-b border-[#334155]/50 transition-colors hover:bg-[#334155]/20">
                  <td className="px-4 py-2.5 font-mono text-[#F3F4F6]">{w.worker}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-[#F3F4F6]">{w.avgMs.toLocaleString()}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-[#F59E0B]">{w.p95Ms.toLocaleString()}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-[#9CA3AF]">{w.count.toLocaleString()}</td>
                </tr>
              ))}
              {data.byWorker.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-[#9CA3AF]">해당 기간에 성능 데이터가 없습니다</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
