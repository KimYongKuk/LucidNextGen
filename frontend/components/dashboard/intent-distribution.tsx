"use client"

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import { SectionHeader } from "./section-header"
import type { IntentsData } from "@/lib/api/report"

const INTENT_COLORS = [
  "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
  "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1",
  "#14B8A6", "#A855F7",
]

interface Props {
  data: IntentsData
  onIntentClick?: (intentKey: string, intentName: string) => void
}

export function IntentDistribution({ data, onIntentClick }: Props) {
  const items = data.distribution

  const handleRowClick = (intentKey: string, name: string) => {
    if (onIntentClick) onIntentClick(intentKey, name)
  }

  return (
    <section>
      <SectionHeader title="의도 분류 분포" subtitle="Intent Distribution" />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Pie Chart */}
        <div className="rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
          <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">카테고리별 비율</h3>
          <ResponsiveContainer width="100%" height={360}>
            <PieChart>
              <Pie
                data={items}
                dataKey="count"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={130}
                innerRadius={60}
                paddingAngle={2}
                strokeWidth={0}
                style={{ cursor: onIntentClick ? "pointer" : "default" }}
                onClick={(_, index) => {
                  const item = items[index]
                  if (item) handleRowClick(item.intentKey, item.name)
                }}
              >
                {items.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={INTENT_COLORS[index % INTENT_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #334155", borderRadius: "8px", color: "#F3F4F6" }}
                formatter={(value, name) => [`${value}건`, name]}
              />
              <Legend
                wrapperStyle={{ fontSize: 11, color: "#9CA3AF" }}
                layout="horizontal"
                verticalAlign="bottom"
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Table */}
        <div className="rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
          <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">카테고리별 상세 <span className="text-xs text-[#6B7280]">(클릭하여 상세 보기)</span></h3>
          <div className="overflow-hidden rounded-lg border border-[#334155]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#334155] bg-[#0F172A]/50">
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">카테고리</th>
                  <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">건수</th>
                  <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">비율</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => (
                  <tr
                    key={item.name}
                    className="cursor-pointer border-b border-[#334155]/50 transition-colors hover:bg-[#334155]/30"
                    onClick={() => handleRowClick(item.intentKey, item.name)}
                  >
                    <td className="px-4 py-2.5 text-[#F3F4F6]">
                      <div className="flex items-center gap-2">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: INTENT_COLORS[index % INTENT_COLORS.length] }}
                        />
                        {item.name}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[#F3F4F6]">{item.count.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-[#9CA3AF]">{item.ratio}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  )
}
