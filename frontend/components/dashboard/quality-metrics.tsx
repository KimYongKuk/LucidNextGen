"use client"

import { AlertTriangle, Percent } from "lucide-react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts"
import { KpiCard } from "./kpi-card"
import { SectionHeader } from "./section-header"
import type { QualityData } from "@/lib/api/report"

interface Props {
  data: QualityData
}

export function QualityMetrics({ data }: Props) {
  return (
    <section>
      <SectionHeader title="답변 품질" subtitle="Answer Quality" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <KpiCard label="답변 실패 건수" value={data.failCount} icon={AlertTriangle} accent="red" />
        <KpiCard label="답변 실패율" value={`${data.failRate}%`} icon={Percent} accent="red" />
      </div>

      {/* Category Failure Rate Bar Chart */}
      <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
        <h3 className="mb-1 text-sm font-medium text-[#9CA3AF]">카테고리별 답변 실패율 (%)</h3>
        <p className="mb-4 text-xs text-[#6B7280]">사내문서/IT/회계 검색 실패 + 명시적 에러</p>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={data.failByCategory} layout="vertical" margin={{ top: 5, right: 30, bottom: 5, left: 90 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
            <XAxis type="number" tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} unit="%" />
            <YAxis dataKey="category" type="category" tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} width={85} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #334155", borderRadius: "8px", color: "#F3F4F6" }}
              formatter={(value, _name, entry) => {
                const item = entry?.payload
                return [`${value}% (${item?.failCount || 0}/${item?.total || 0}건)`, "실패율"]
              }}
            />
            <Bar dataKey="failRate" radius={[0, 4, 4, 0]} maxBarSize={24}>
              {data.failByCategory.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.isHighlight ? "#EF4444" : "#3B82F6"}
                  fillOpacity={entry.isHighlight ? 1 : 0.7}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Recent Failure Samples Table */}
      <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
        <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">최근 답변 실패 샘플</h3>
        <div className="max-h-[400px] overflow-auto rounded-lg border border-[#334155]">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="border-b border-[#334155] bg-[#0F172A]">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">일시</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">사용자</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">질문</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">답변 (미리보기)</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">카테고리</th>
              </tr>
            </thead>
            <tbody>
              {data.recentFailures.map((row, i) => (
                <tr key={i} className="border-b border-[#334155]/50 transition-colors hover:bg-[#334155]/20">
                  <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-[#9CA3AF]">{row.datetime}</td>
                  <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-[#F3F4F6]">{row.userId}</td>
                  <td className="max-w-[200px] truncate px-4 py-2.5 text-[#F3F4F6]" title={row.question}>{row.question}</td>
                  <td className="max-w-[200px] truncate px-4 py-2.5 text-[#9CA3AF]" title={row.answer}>{row.answer}</td>
                  <td className="px-4 py-2.5">
                    <span className="rounded-full bg-[#EF4444]/10 px-2.5 py-0.5 text-xs font-medium text-[#EF4444]">
                      {row.category}
                    </span>
                  </td>
                </tr>
              ))}
              {data.recentFailures.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-[#9CA3AF]">해당 기간에 답변 실패 건이 없습니다</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
