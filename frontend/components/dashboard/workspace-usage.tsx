"use client"

import { Layers, MessageCircle, Database, FileText } from "lucide-react"
import { KpiCard } from "./kpi-card"
import { SectionHeader } from "./section-header"
import type { WorkspacesData } from "@/lib/api/report"

type Tab = "messages" | "documents"

interface Props {
  data: WorkspacesData
  onWorkspaceClick?: (workspaceId: string, workspaceName: string, tab: Tab) => void
}

export function WorkspaceUsage({ data, onWorkspaceClick }: Props) {
  return (
    <section>
      <SectionHeader title="워크스페이스 활용" subtitle="Workspace Activity" />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        <KpiCard label="활성 워크스페이스" value={data.activeWorkspaces} icon={Layers} accent="blue" />
        <KpiCard label="총 세션 수" value={data.totalSessions} icon={MessageCircle} accent="green" />
        <KpiCard label="메모리 업데이트" value={data.memoryUpdates} icon={Database} accent="purple" />
      </div>

      <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
        <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">상위 워크스페이스</h3>
        <div className="overflow-hidden rounded-lg border border-[#334155]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#334155] bg-[#0F172A]/50">
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">워크스페이스</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-[#9CA3AF]">사용자</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">메시지 수</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">문서 수</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-[#9CA3AF]">최근 활동</th>
              </tr>
            </thead>
            <tbody>
              {data.topWorkspaces.map((ws) => (
                <tr key={ws.workspaceId} className="border-b border-[#334155]/50 transition-colors hover:bg-[#334155]/20">
                  <td className="px-4 py-2.5 font-medium text-[#F3F4F6]">{ws.name}</td>
                  <td className="px-4 py-2.5 text-[#9CA3AF]">{ws.user}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-[#F3F4F6]">
                    <button
                      onClick={() => onWorkspaceClick?.(ws.workspaceId, ws.name, "messages")}
                      className="rounded px-1.5 py-0.5 text-[#3B82F6] transition-colors hover:bg-[#3B82F6]/10 hover:underline"
                    >
                      {ws.messages.toLocaleString()}
                    </button>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-[#F3F4F6]">
                    <button
                      onClick={() => onWorkspaceClick?.(ws.workspaceId, ws.name, "documents")}
                      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[#3B82F6] transition-colors hover:bg-[#3B82F6]/10 hover:underline"
                    >
                      <FileText className="h-3 w-3 text-[#9CA3AF]" />
                      {ws.documents}
                    </button>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs text-[#9CA3AF]">{ws.lastActive}</td>
                </tr>
              ))}
              {data.topWorkspaces.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-[#9CA3AF]">해당 기간에 워크스페이스 활동이 없습니다</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}
