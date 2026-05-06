"use client"

import { useEffect, useState } from "react"
import { X, Loader2 } from "lucide-react"
import { reportApi, type UserDetailData } from "@/lib/api/report"
import { useUserInfo, formatUserDisplay } from "@/hooks/use-user-directory"

interface Props {
  userId: string
  dateFrom: string
  dateTo: string
  onClose: () => void
}

export function UserDetailModal({ userId, dateFrom, dateTo, onClose }: Props) {
  const [data, setData] = useState<UserDetailData | null>(null)
  const userInfo = useUserInfo(userId)
  const displayName = formatUserDisplay(userId, userInfo)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    reportApi.getUserDetail(dateFrom, dateTo, userId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [userId, dateFrom, dateTo])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="relative mx-4 max-h-[80vh] w-full max-w-5xl overflow-hidden rounded-2xl border border-[#334155] bg-[#1F2937] shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#334155] px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-[#F3F4F6]">
              {displayName}
              <span className="ml-2 font-mono text-xs text-[#64748B]">({userId})</span>
              <span className="ml-1.5 text-sm">활동 상세</span>
            </h2>
            <p className="text-xs text-[#9CA3AF]">{dateFrom} ~ {dateTo} | 최근 50건</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-[#9CA3AF] transition-colors hover:bg-[#334155] hover:text-[#F3F4F6]">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[calc(80vh-72px)] overflow-auto p-6">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-[#3B82F6]" />
              <span className="ml-2 text-sm text-[#9CA3AF]">불러오는 중...</span>
            </div>
          )}

          {!loading && data && data.messages.length === 0 && (
            <p className="py-12 text-center text-[#9CA3AF]">해당 기간에 데이터가 없습니다</p>
          )}

          {!loading && data && data.messages.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-[#334155]">
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10">
                  <tr className="border-b border-[#334155] bg-[#0F172A]">
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">일시</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">질문</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">답변 (미리보기)</th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">기능</th>
                    <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">응답(ms)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.messages.map((msg, i) => (
                    <tr key={i} className="border-b border-[#334155]/50 transition-colors hover:bg-[#334155]/20">
                      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-[#9CA3AF]">{msg.datetime}</td>
                      <td className="max-w-[220px] truncate px-4 py-2.5 text-[#F3F4F6]" title={msg.question}>{msg.question}</td>
                      <td className="max-w-[260px] truncate px-4 py-2.5 text-[#9CA3AF]" title={msg.answer}>{msg.answer}</td>
                      <td className="px-4 py-2.5">
                        <span className="rounded-full bg-[#3B82F6]/10 px-2.5 py-0.5 text-xs font-medium text-[#3B82F6]">
                          {msg.intent}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-xs text-[#9CA3AF]">
                        {msg.responseTimeMs ? `${(msg.responseTimeMs / 1000).toFixed(1)}s` : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
