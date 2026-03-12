"use client"

import { useEffect, useState } from "react"
import { X, Loader2, MessageCircle, FileText } from "lucide-react"
import { reportApi, type WorkspaceDetailData } from "@/lib/api/report"

type Tab = "messages" | "documents"

interface Props {
  workspaceId: string
  workspaceName: string
  dateFrom: string
  dateTo: string
  initialTab: Tab
  onClose: () => void
}

export function WorkspaceDetailModal({ workspaceId, workspaceName, dateFrom, dateTo, initialTab, onClose }: Props) {
  const [tab, setTab] = useState<Tab>(initialTab)
  const [data, setData] = useState<WorkspaceDetailData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    reportApi.getWorkspaceDetail(dateFrom, dateTo, workspaceId, tab)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [workspaceId, dateFrom, dateTo, tab])

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
            <h2 className="text-lg font-semibold text-[#F3F4F6]">{workspaceName}</h2>
            <p className="text-xs text-[#9CA3AF]">{dateFrom} ~ {dateTo}</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-[#9CA3AF] transition-colors hover:bg-[#334155] hover:text-[#F3F4F6]">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-[#334155] px-6">
          <button
            onClick={() => setTab("messages")}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === "messages"
                ? "border-b-2 border-[#3B82F6] text-[#3B82F6]"
                : "text-[#9CA3AF] hover:text-[#F3F4F6]"
            }`}
          >
            <MessageCircle className="h-3.5 w-3.5" />
            메시지
          </button>
          <button
            onClick={() => setTab("documents")}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === "documents"
                ? "border-b-2 border-[#3B82F6] text-[#3B82F6]"
                : "text-[#9CA3AF] hover:text-[#F3F4F6]"
            }`}
          >
            <FileText className="h-3.5 w-3.5" />
            문서
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[calc(80vh-130px)] overflow-auto p-6">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-[#3B82F6]" />
              <span className="ml-2 text-sm text-[#9CA3AF]">불러오는 중...</span>
            </div>
          )}

          {!loading && tab === "messages" && (
            <MessagesTab messages={data?.messages ?? []} />
          )}

          {!loading && tab === "documents" && (
            <DocumentsTab documents={data?.documents ?? []} />
          )}
        </div>
      </div>
    </div>
  )
}

function MessagesTab({ messages }: { messages: NonNullable<WorkspaceDetailData["messages"]> }) {
  if (messages.length === 0) {
    return <p className="py-12 text-center text-[#9CA3AF]">해당 기간에 메시지가 없습니다</p>
  }

  return (
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
          {messages.map((msg, i) => (
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
  )
}

function DocumentsTab({ documents }: { documents: NonNullable<WorkspaceDetailData["documents"]> }) {
  if (documents.length === 0) {
    return <p className="py-12 text-center text-[#9CA3AF]">업로드된 문서가 없습니다</p>
  }

  const typeColors: Record<string, string> = {
    pdf: "text-[#EF4444] bg-[#EF4444]/10",
    docx: "text-[#3B82F6] bg-[#3B82F6]/10",
    xlsx: "text-[#22C55E] bg-[#22C55E]/10",
    pptx: "text-[#F97316] bg-[#F97316]/10",
    txt: "text-[#9CA3AF] bg-[#9CA3AF]/10",
  }

  return (
    <div className="overflow-hidden rounded-lg border border-[#334155]">
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10">
          <tr className="border-b border-[#334155] bg-[#0F172A]">
            <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">파일명</th>
            <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">유형</th>
            <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">청크 수</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => {
            const ext = doc.fileType.toLowerCase()
            const colorClass = typeColors[ext] ?? typeColors.txt
            return (
              <tr key={doc.fileId} className="border-b border-[#334155]/50 transition-colors hover:bg-[#334155]/20">
                <td className="px-4 py-2.5 text-[#F3F4F6]">
                  <span className="inline-flex items-center gap-1.5">
                    <FileText className="h-3.5 w-3.5 text-[#9CA3AF]" />
                    {doc.fileName}
                  </span>
                </td>
                <td className="px-4 py-2.5">
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium uppercase ${colorClass}`}>
                    {ext}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-[#9CA3AF]">{doc.chunks}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
