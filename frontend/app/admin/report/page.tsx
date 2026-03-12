"use client"

import { useState, useCallback, useRef } from "react"
import Link from "next/link"
import { ArrowLeft, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DateRangeSelector } from "@/components/dashboard/date-range-selector"
import { UsageOverview } from "@/components/dashboard/usage-overview"
import { IntentDistribution } from "@/components/dashboard/intent-distribution"
import { IntentDetailModal } from "@/components/dashboard/intent-detail-modal"
import { UserDetailModal } from "@/components/dashboard/user-detail-modal"
import { QualityMetrics } from "@/components/dashboard/quality-metrics"
import { WorkspaceUsage } from "@/components/dashboard/workspace-usage"
import { WorkspaceDetailModal } from "@/components/dashboard/workspace-detail-modal"
import { FilesGenerated } from "@/components/dashboard/files-generated"
import { PerformanceSection } from "@/components/dashboard/performance-section"
import { TokenUsage } from "@/components/dashboard/token-usage"
import { UserRanking } from "@/components/dashboard/user-ranking"
import { EmailSettings } from "@/components/dashboard/email-settings"
import { fetchAllReportData, type AllReportData } from "@/lib/api/report"

export default function ReportPage() {
  const [data, setData] = useState<AllReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Intent detail modal state
  const [intentModal, setIntentModal] = useState<{ intentKey: string; intentName: string } | null>(null)

  // User detail modal state
  const [userModal, setUserModal] = useState<string | null>(null)

  // Workspace detail modal state
  const [wsModal, setWsModal] = useState<{ workspaceId: string; name: string; tab: "messages" | "documents" } | null>(null)

  // Keep current date range for modal API calls
  const dateRangeRef = useRef({ from: "", to: "" })

  const handleRangeChange = useCallback(async (dateFrom: string, dateTo: string) => {
    dateRangeRef.current = { from: dateFrom, to: dateTo }
    setLoading(true)
    setError(null)
    try {
      const result = await fetchAllReportData(dateFrom, dateTo)
      setData(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : "데이터를 불러오는 중 오류가 발생했습니다")
    } finally {
      setLoading(false)
    }
  }, [])

  const handleIntentClick = useCallback((intentKey: string, intentName: string) => {
    setIntentModal({ intentKey, intentName })
  }, [])

  const handleUserClick = useCallback((userId: string) => {
    setUserModal(userId)
  }, [])

  const handleWorkspaceClick = useCallback((workspaceId: string, name: string, tab: "messages" | "documents") => {
    setWsModal({ workspaceId, name, tab })
  }, [])

  return (
    <div className="min-h-screen bg-[#0F172A] report-text-sharp">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-[#334155]/50 bg-[#0F172A]/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <Button asChild variant="ghost" size="sm" className="text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#334155]/50">
              <Link href="/admin">
                <ArrowLeft className="mr-1 h-4 w-4" />
                관리자
              </Link>
            </Button>
            <div className="h-6 w-px bg-[#334155]" />
            <div>
              <h1 className="text-base font-semibold text-[#F3F4F6]">Lucid AI Service Report</h1>
              <p className="text-xs text-[#9CA3AF]">서비스 레포트 대시보드</p>
            </div>
          </div>
          <DateRangeSelector onRangeChange={handleRangeChange} />
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-7xl space-y-10 px-4 py-8 sm:px-6 lg:px-8">
        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-[#3B82F6]" />
            <span className="ml-3 text-[#9CA3AF]">데이터를 불러오는 중...</span>
          </div>
        )}

        {error && !loading && (
          <div className="rounded-xl border border-[#EF4444]/30 bg-[#EF4444]/10 p-6 text-center">
            <p className="text-[#EF4444]">{error}</p>
            <p className="mt-2 text-sm text-[#9CA3AF]">백엔드 서버가 실행 중인지 확인해주세요</p>
          </div>
        )}

        {data && !loading && (
          <>
            <UsageOverview data={data.overview} />
            <UserRanking data={data.userRanking} onUserClick={handleUserClick} />
            <IntentDistribution data={data.intents} onIntentClick={handleIntentClick} />
            <QualityMetrics data={data.quality} />
            <WorkspaceUsage data={data.workspaces} onWorkspaceClick={handleWorkspaceClick} />
            <FilesGenerated data={data.artifacts} />
            <PerformanceSection data={data.performance} />
            <TokenUsage data={data.tokenUsage} />
          </>
        )}

        {/* 이메일 설정은 데이터 로딩과 무관하게 항상 표시 */}
        {!loading && <EmailSettings />}
      </main>

      {/* Intent Detail Modal */}
      {intentModal && (
        <IntentDetailModal
          intentKey={intentModal.intentKey}
          intentName={intentModal.intentName}
          dateFrom={dateRangeRef.current.from}
          dateTo={dateRangeRef.current.to}
          onClose={() => setIntentModal(null)}
        />
      )}

      {/* User Detail Modal */}
      {userModal && (
        <UserDetailModal
          userId={userModal}
          dateFrom={dateRangeRef.current.from}
          dateTo={dateRangeRef.current.to}
          onClose={() => setUserModal(null)}
        />
      )}

      {/* Workspace Detail Modal */}
      {wsModal && (
        <WorkspaceDetailModal
          workspaceId={wsModal.workspaceId}
          workspaceName={wsModal.name}
          dateFrom={dateRangeRef.current.from}
          dateTo={dateRangeRef.current.to}
          initialTab={wsModal.tab}
          onClose={() => setWsModal(null)}
        />
      )}

      {/* Footer */}
      <footer className="border-t border-[#334155]/50 py-6 text-center text-xs text-[#9CA3AF]">
        <span>AI Chatbot Admin Dashboard</span>
        <span className="mx-2">{'·'}</span>
        <span>LFChatbot Service Report</span>
      </footer>
    </div>
  )
}
