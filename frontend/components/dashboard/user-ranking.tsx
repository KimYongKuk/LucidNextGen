"use client"

import { Users, MessageSquare } from "lucide-react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import { KpiCard } from "./kpi-card"
import { SectionHeader } from "./section-header"
import type { UserRankingData } from "@/lib/api/report"
import { useUserDirectory, formatUserDisplay } from "@/hooks/use-user-directory"

interface Props {
  data: UserRankingData
  onUserClick?: (userId: string) => void
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  if (n === 0) return "-"
  return n.toLocaleString()
}

export function UserRanking({ data, onUserClick }: Props) {
  const avgMessages = data.totalUsers > 0
    ? Math.round(data.totalMessages / data.totalUsers)
    : 0

  // 사번 → 이름/부서 매핑 (배치 lookup)
  const userIds = data.ranking.map((u) => u.userId)
  const directory = useUserDirectory(userIds)

  const chartData = data.ranking.slice(0, 10).map((u) => ({
    ...u,
    displayName: formatUserDisplay(u.userId, directory[u.userId]),
  }))

  return (
    <section>
      <SectionHeader title="사용자 랭킹" subtitle="대화량 기준 사용자 순위" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <KpiCard label="전체 사용자 수" value={data.totalUsers} icon={Users} accent="blue" />
        <KpiCard label="사용자당 평균 메시지" value={avgMessages} icon={MessageSquare} accent="green" />
      </div>

      {/* Horizontal Bar Chart - Top 10 */}
      {chartData.length > 0 && (
        <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
          <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">
            상위 {chartData.length}명 메시지 수
          </h3>
          <ResponsiveContainer width="100%" height={Math.max(200, chartData.length * 36)}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 5, right: 30, bottom: 5, left: 80 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: "#9CA3AF", fontSize: 12 }}
                axisLine={{ stroke: "#334155" }}
                tickLine={false}
              />
              <YAxis
                dataKey="displayName"
                type="category"
                tick={{ fill: "#9CA3AF", fontSize: 12 }}
                axisLine={{ stroke: "#334155" }}
                tickLine={false}
                width={140}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1F2937",
                  border: "1px solid #334155",
                  borderRadius: "8px",
                  color: "#F3F4F6",
                }}
                formatter={(value) => [`${(value ?? 0).toLocaleString()}건`, "메시지"]}
              />
              <Bar
                dataKey="messageCount"
                fill="#3B82F6"
                radius={[0, 4, 4, 0]}
                maxBarSize={24}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Full ranking table */}
      <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
        <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">사용자별 상세 활동</h3>
        <div className="max-h-[500px] overflow-auto rounded-lg border border-[#334155]">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="border-b border-[#334155] bg-[#0F172A]">
                <th className="px-4 py-2.5 text-center text-xs font-medium text-[#9CA3AF]">순위</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">사용자</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">메시지 수</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">토큰</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">세션 수</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">주 사용 기능</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">최근 활동</th>
              </tr>
            </thead>
            <tbody>
              {data.ranking.map((user) => (
                <tr
                  key={user.userId}
                  className="border-b border-[#334155]/50 transition-colors hover:bg-[#334155]/20 cursor-pointer"
                  onClick={() => onUserClick?.(user.userId)}
                >
                  <td className="px-4 py-2.5 text-center">
                    {user.rank <= 3 ? (
                      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[#F59E0B]/10 text-xs font-bold text-[#F59E0B]">
                        {user.rank}
                      </span>
                    ) : (
                      <span className="font-mono text-[#9CA3AF]">{user.rank}</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-[#3B82F6] underline decoration-[#3B82F6]/30">
                    {formatUserDisplay(user.userId, directory[user.userId])}
                    <span className="ml-1.5 font-mono text-[10px] text-[#64748B]">({user.userId})</span>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono font-medium text-[#3B82F6]">
                    {user.messageCount.toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-[#F59E0B]">
                    {formatTokens(user.totalTokens || 0)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-[#F3F4F6]">
                    {user.sessionCount.toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="rounded-full bg-[#3B82F6]/10 px-2.5 py-0.5 text-xs font-medium text-[#3B82F6]">
                      {user.favoriteIntent}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs text-[#9CA3AF]">
                    {user.lastActive}
                  </td>
                </tr>
              ))}
              {data.ranking.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-[#9CA3AF]">
                    해당 기간에 사용자 활동이 없습니다
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
