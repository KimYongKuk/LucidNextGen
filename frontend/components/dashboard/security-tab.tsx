"use client"

import { useEffect, useState, useCallback } from "react"
import {
  Shield,
  ShieldAlert,
  ShieldX,
  Lock,
  AlertTriangle,
  Activity,
  Users,
  Zap,
  Loader2,
  Eye,
  Unlock,
} from "lucide-react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
} from "recharts"
import { KpiCard } from "./kpi-card"
import { SectionHeader } from "./section-header"
import {
  fetchSecurityStats,
  fetchSecurityEvents,
  fetchSecurityBlocks,
  fetchLlmUsage,
  fetchSecurityEventDetail,
  unblockUser,
  dryRunCheck,
  type SecurityStats,
  type SecurityEvent,
  type SecurityEventDetail,
  type SecurityBlock,
  type LlmUsage,
} from "@/lib/api/security"
import { useUserDirectory, formatUserDisplay } from "@/hooks/use-user-directory"

interface Props {
  dateFrom: string
  dateTo: string
  adminId: string
}

const THREAT_COLORS: Record<string, string> = {
  INJECTION: "#EF4444",
  JAILBREAK: "#F59E0B",
  DATA_EXFIL: "#8B5CF6",
  PRIVILEGE_ESCALATION: "#EC4899",
  ABUSE: "#3B82F6",
  MALICIOUS_CONTENT: "#DC2626",
  OTHER: "#6B7280",
}

const THREAT_LABELS: Record<string, string> = {
  INJECTION: "프롬프트 인젝션",
  JAILBREAK: "제약 우회",
  DATA_EXFIL: "데이터 추출",
  PRIVILEGE_ESCALATION: "권한 탈취",
  ABUSE: "호출 남용",
  MALICIOUS_CONTENT: "악성 콘텐츠",
  OTHER: "기타",
}

const ACTION_LABELS: Record<string, string> = {
  LOGGED: "기록",
  WARNED: "경고",
  BLOCKED_REQUEST: "요청 거부",
  TEMP_BLOCKED: "일시 차단",
  PERM_BLOCKED: "영구 차단",
}

const ACTION_COLORS: Record<string, string> = {
  LOGGED: "#6B7280",
  WARNED: "#F59E0B",
  BLOCKED_REQUEST: "#EF4444",
  TEMP_BLOCKED: "#DC2626",
  PERM_BLOCKED: "#7F1D1D",
}

export function SecurityTab({ dateFrom, dateTo, adminId }: Props) {
  const [stats, setStats] = useState<SecurityStats | null>(null)
  const [events, setEvents] = useState<SecurityEvent[]>([])
  const [blocks, setBlocks] = useState<SecurityBlock[]>([])
  const [llmUsage, setLlmUsage] = useState<LlmUsage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [eventDetail, setEventDetail] = useState<SecurityEventDetail | null>(null)
  const [dryRunMsg, setDryRunMsg] = useState("")
  const [dryRunResult, setDryRunResult] = useState<any>(null)
  const [dryRunLoading, setDryRunLoading] = useState(false)

  // 사번 → 이름/부서 매핑
  const userIds = [
    ...(stats?.top_offenders?.map((u) => u.user_id) ?? []),
    ...blocks.map((b) => b.user_id),
    ...events.map((e) => e.user_id),
    ...(eventDetail ? [eventDetail.user_id] : []),
  ]
  const directory = useUserDirectory(userIds)

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, e, b, l] = await Promise.all([
        fetchSecurityStats(dateFrom, dateTo),
        fetchSecurityEvents({ date_from: dateFrom, date_to: dateTo, limit: 50 }),
        fetchSecurityBlocks(false),
        fetchLlmUsage(),
      ])
      setStats(s)
      setEvents(e.events)
      setBlocks(b.blocks)
      setLlmUsage(l)
    } catch (err) {
      setError(err instanceof Error ? err.message : "데이터 로딩 실패")
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo])

  useEffect(() => {
    if (dateFrom && dateTo) loadAll()
  }, [dateFrom, dateTo, loadAll])

  const handleUnblock = async (userId: string) => {
    const reason = window.prompt(`사용자 ${userId} 차단 해제 사유:`, "관리자 수동 해제")
    if (!reason) return
    try {
      await unblockUser(userId, adminId, reason)
      await loadAll()
      alert(`사용자 ${userId} 차단이 해제되었습니다.`)
    } catch (e) {
      alert(`차단 해제 실패: ${e instanceof Error ? e.message : "알 수 없는 오류"}`)
    }
  }

  const handleDryRun = async () => {
    if (!dryRunMsg.trim()) return
    setDryRunLoading(true)
    try {
      const r = await dryRunCheck(dryRunMsg)
      setDryRunResult(r)
    } catch (e) {
      setDryRunResult({ error: e instanceof Error ? e.message : "실패" })
    } finally {
      setDryRunLoading(false)
    }
  }

  const handleEventClick = async (id: number) => {
    try {
      const detail = await fetchSecurityEventDetail(id)
      setEventDetail(detail)
    } catch (e) {
      alert(`상세 조회 실패: ${e}`)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-[#3B82F6]" />
        <span className="ml-3 text-[#9CA3AF]">보안 데이터를 불러오는 중...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-[#EF4444]/30 bg-[#EF4444]/10 p-6 text-center">
        <p className="text-[#EF4444]">{error}</p>
      </div>
    )
  }

  if (!stats || !llmUsage) return null

  const threatPieData = stats.by_threat_type.map((t) => ({
    name: THREAT_LABELS[t.threat_type] || t.threat_type,
    value: t.count,
    threat: t.threat_type,
  }))

  return (
    <div className="space-y-10">
      {/* KPI Cards */}
      <section>
        <SectionHeader title="보안 현황" subtitle="Security Overview" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <KpiCard label="전체 이벤트" value={stats.summary.total} icon={Activity} accent="blue" />
          <KpiCard label="경고" value={stats.summary.warned} icon={AlertTriangle} accent="orange" />
          <KpiCard label="요청 거부" value={stats.summary.blocked_req} icon={ShieldX} accent="red" />
          <KpiCard label="일시/영구 차단" value={stats.summary.temp_blocked + stats.summary.perm_blocked} icon={Lock} accent="red" />
          <KpiCard label="현재 차단자" value={stats.active_blocks} icon={Users} accent="purple" />
        </div>
      </section>

      {/* LLM Usage */}
      <section>
        <SectionHeader title="LLM 판정 사용량" subtitle="일일 Haiku 호출 한도 모니터링" />
        <div className="rounded-xl border border-[#334155] bg-[#1F2937]/80 p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-[#9CA3AF]">오늘 ({llmUsage.today.date})</p>
              <p className="mt-1 text-2xl font-bold text-[#F3F4F6]">
                {llmUsage.today.count.toLocaleString()} / {llmUsage.today.limit.toLocaleString()}
              </p>
              <p className="mt-1 text-xs text-[#9CA3AF]">
                남은 한도: {llmUsage.today.remaining.toLocaleString()}회 ({100 - llmUsage.today.pct}%)
              </p>
            </div>
            <Zap className={`h-12 w-12 ${llmUsage.today.pct > 80 ? "text-[#EF4444]" : "text-[#3B82F6]"}`} />
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#334155]">
            <div
              className={`h-full transition-all ${
                llmUsage.today.pct > 80 ? "bg-[#EF4444]" : llmUsage.today.pct > 50 ? "bg-[#F59E0B]" : "bg-[#3B82F6]"
              }`}
              style={{ width: `${Math.min(100, llmUsage.today.pct)}%` }}
            />
          </div>
        </div>
      </section>

      {/* Charts */}
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Daily trend */}
        <div className="rounded-xl border border-[#334155] bg-[#1F2937]/80 p-5">
          <h3 className="mb-4 text-sm font-semibold text-[#F3F4F6]">일별 이벤트 추이</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={stats.daily}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="day" stroke="#9CA3AF" fontSize={11} />
              <YAxis stroke="#9CA3AF" fontSize={11} />
              <Tooltip contentStyle={{ background: "#0F172A", border: "1px solid #334155" }} />
              <Line type="monotone" dataKey="count" stroke="#EF4444" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Threat type distribution */}
        <div className="rounded-xl border border-[#334155] bg-[#1F2937]/80 p-5">
          <h3 className="mb-4 text-sm font-semibold text-[#F3F4F6]">위협 유형 분포</h3>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie
                data={threatPieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={(e: any) => `${e.name} (${e.value})`}
              >
                {threatPieData.map((d, i) => (
                  <Cell key={i} fill={THREAT_COLORS[d.threat] || "#6B7280"} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: "#0F172A", border: "1px solid #334155" }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Top Users */}
      {stats.top_users.length > 0 && (
        <section>
          <SectionHeader title="상위 위반 사용자" subtitle="Top Violators" />
          <div className="rounded-xl border border-[#334155] bg-[#1F2937]/80 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[#0F172A]">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#9CA3AF]">사용자</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#9CA3AF]">이벤트 수</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#9CA3AF]">최고 심각도</th>
                </tr>
              </thead>
              <tbody>
                {stats.top_users.map((u) => (
                  <tr key={u.user_id} className="border-t border-[#334155]">
                    <td className="px-4 py-3 text-[#F3F4F6]">
                      {formatUserDisplay(u.user_id, directory[u.user_id])}
                      <span className="ml-1.5 font-mono text-[10px] text-[#64748B]">({u.user_id})</span>
                    </td>
                    <td className="px-4 py-3 text-right text-[#F3F4F6]">{u.count}</td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-semibold ${
                          u.max_severity >= 85
                            ? "bg-[#7F1D1D]/30 text-[#FCA5A5]"
                            : u.max_severity >= 70
                            ? "bg-[#DC2626]/20 text-[#FCA5A5]"
                            : u.max_severity >= 50
                            ? "bg-[#EF4444]/20 text-[#FCA5A5]"
                            : "bg-[#F59E0B]/20 text-[#FCD34D]"
                        }`}
                      >
                        {u.max_severity}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Current Blocks */}
      <section>
        <SectionHeader title="현재 차단된 사용자" subtitle={`${blocks.length}명`} />
        {blocks.length === 0 ? (
          <div className="rounded-xl border border-[#334155] bg-[#1F2937]/80 p-8 text-center text-sm text-[#9CA3AF]">
            차단된 사용자 없음
          </div>
        ) : (
          <div className="rounded-xl border border-[#334155] bg-[#1F2937]/80 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[#0F172A]">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#9CA3AF]">사용자</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#9CA3AF]">유형</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#9CA3AF]">위협</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#9CA3AF]">차단 시각</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-[#9CA3AF]">해제 예정</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-[#9CA3AF]">조치</th>
                </tr>
              </thead>
              <tbody>
                {blocks.map((b) => (
                  <tr key={b.user_id} className="border-t border-[#334155]">
                    <td className="px-4 py-3 text-[#F3F4F6]">
                      {formatUserDisplay(b.user_id, directory[b.user_id])}
                      <span className="ml-1.5 font-mono text-[10px] text-[#64748B]">({b.user_id})</span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-semibold ${
                          b.block_type === "PERMANENT"
                            ? "bg-[#7F1D1D]/40 text-[#FCA5A5]"
                            : "bg-[#F59E0B]/20 text-[#FCD34D]"
                        }`}
                      >
                        {b.block_type === "PERMANENT" ? "영구" : "일시"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[#F3F4F6]">
                      {b.threat_type ? THREAT_LABELS[b.threat_type] || b.threat_type : "-"}
                    </td>
                    <td className="px-4 py-3 text-[#9CA3AF] text-xs">
                      {b.blocked_at ? new Date(b.blocked_at).toLocaleString("ko-KR") : "-"}
                    </td>
                    <td className="px-4 py-3 text-[#9CA3AF] text-xs">
                      {b.expires_at ? new Date(b.expires_at).toLocaleString("ko-KR") : "영구"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleUnblock(b.user_id)}
                        className="inline-flex items-center gap-1 rounded-md bg-[#10B981]/20 px-3 py-1 text-xs font-semibold text-[#6EE7B7] hover:bg-[#10B981]/30"
                      >
                        <Unlock className="h-3 w-3" />
                        해제
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Recent Events */}
      <section>
        <SectionHeader title="최근 보안 이벤트" subtitle={`최근 50건`} />
        {events.length === 0 ? (
          <div className="rounded-xl border border-[#334155] bg-[#1F2937]/80 p-8 text-center text-sm text-[#9CA3AF]">
            이벤트 없음
          </div>
        ) : (
          <div className="rounded-xl border border-[#334155] bg-[#1F2937]/80 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-[#0F172A]">
                <tr>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-[#9CA3AF]">시각</th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-[#9CA3AF]">사용자</th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-[#9CA3AF]">위협</th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-[#9CA3AF]">조치</th>
                  <th className="px-3 py-3 text-right text-xs font-semibold text-[#9CA3AF]">심각도</th>
                  <th className="px-3 py-3 text-left text-xs font-semibold text-[#9CA3AF]">메시지</th>
                  <th className="px-3 py-3 text-center text-xs font-semibold text-[#9CA3AF]">상세</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id} className="border-t border-[#334155] hover:bg-[#0F172A]/50">
                    <td className="px-3 py-2.5 text-xs text-[#9CA3AF]">
                      {e.created_at ? new Date(e.created_at).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "-"}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-[#F3F4F6]">
                      {formatUserDisplay(e.user_id, directory[e.user_id])}
                      <span className="ml-1 font-mono text-[10px] text-[#64748B]">({e.user_id})</span>
                    </td>
                    <td className="px-3 py-2.5 text-xs">
                      <span
                        className="px-1.5 py-0.5 rounded font-medium"
                        style={{
                          backgroundColor: `${THREAT_COLORS[e.threat_type]}20`,
                          color: THREAT_COLORS[e.threat_type],
                        }}
                      >
                        {THREAT_LABELS[e.threat_type] || e.threat_type}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-xs">
                      <span
                        className="px-1.5 py-0.5 rounded font-medium"
                        style={{
                          backgroundColor: `${ACTION_COLORS[e.action_taken]}20`,
                          color: ACTION_COLORS[e.action_taken],
                        }}
                      >
                        {ACTION_LABELS[e.action_taken] || e.action_taken}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-right text-xs font-semibold text-[#F3F4F6]">{e.severity}</td>
                    <td className="px-3 py-2.5 max-w-md truncate text-xs text-[#9CA3AF]">
                      {e.user_message_snippet || "-"}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <button
                        onClick={() => handleEventClick(e.id)}
                        className="inline-flex items-center text-[#3B82F6] hover:text-[#60A5FA]"
                      >
                        <Eye className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Dry-Run Test */}
      <section>
        <SectionHeader title="판정 테스트 (Dry-Run)" subtitle="차단 없이 분류 결과만 확인" />
        <div className="rounded-xl border border-[#334155] bg-[#1F2937]/80 p-5">
          <textarea
            value={dryRunMsg}
            onChange={(e) => setDryRunMsg(e.target.value)}
            placeholder="테스트 메시지 입력..."
            className="w-full rounded-lg border border-[#334155] bg-[#0F172A] px-3 py-2 text-sm text-[#F3F4F6] placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
            rows={3}
          />
          <button
            onClick={handleDryRun}
            disabled={dryRunLoading || !dryRunMsg.trim()}
            className="mt-3 inline-flex items-center gap-2 rounded-md bg-[#3B82F6] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {dryRunLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Shield className="h-4 w-4" />}
            판정 실행
          </button>

          {dryRunResult && (
            <div className="mt-4 space-y-2 rounded-lg border border-[#334155] bg-[#0F172A] p-4 text-xs font-mono">
              <div className="text-[#9CA3AF]">
                <span className="text-[#F3F4F6] font-semibold">Rule:</span> score=
                <span className="text-[#EF4444]">{dryRunResult.rule?.suspicion_score}</span>, type={dryRunResult.rule?.threat_type || "NONE"}
                {dryRunResult.rule?.matched_patterns?.length > 0 && (
                  <div className="mt-1 ml-4 text-[#6B7280]">matched: {JSON.stringify(dryRunResult.rule.matched_patterns)}</div>
                )}
              </div>
              {dryRunResult.llm && (
                <div className="text-[#9CA3AF]">
                  <span className="text-[#F3F4F6] font-semibold">LLM:</span>{" "}
                  {dryRunResult.llm.error ? (
                    <span className="text-[#EF4444]">error: {dryRunResult.llm.error}</span>
                  ) : (
                    <>
                      type={dryRunResult.llm.threat_type}, severity=
                      <span className="text-[#EF4444]">{dryRunResult.llm.severity}</span>
                      {dryRunResult.llm.reason && <div className="mt-1 ml-4 text-[#6B7280]">reason: {dryRunResult.llm.reason}</div>}
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Event Detail Modal */}
      {eventDetail && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setEventDetail(null)}
        >
          <div
            className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-xl border border-[#334155] bg-[#0F172A] p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-[#F3F4F6]">이벤트 #{eventDetail.id}</h3>
              <button
                onClick={() => setEventDetail(null)}
                className="text-[#9CA3AF] hover:text-[#F3F4F6]"
              >
                ✕
              </button>
            </div>
            <div className="space-y-3 text-sm">
              <DetailRow label="사용자" value={`${formatUserDisplay(eventDetail.user_id, directory[eventDetail.user_id])} (${eventDetail.user_id})`} />
              <DetailRow label="세션" value={eventDetail.session_id || "-"} />
              <DetailRow label="위협 유형" value={THREAT_LABELS[eventDetail.threat_type] || eventDetail.threat_type} />
              <DetailRow label="조치" value={ACTION_LABELS[eventDetail.action_taken] || eventDetail.action_taken} />
              <DetailRow label="심각도" value={`${eventDetail.severity}/100`} />
              <DetailRow label="탐지 레이어" value={eventDetail.detection_layer} />
              <DetailRow label="시각" value={eventDetail.created_at ? new Date(eventDetail.created_at).toLocaleString("ko-KR") : "-"} />
              <div>
                <p className="mb-1 text-xs font-semibold text-[#9CA3AF]">사용자 메시지</p>
                <div className="rounded bg-[#1F2937] p-3 font-mono text-xs text-[#F3F4F6] whitespace-pre-wrap">
                  {eventDetail.user_message || "-"}
                </div>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold text-[#9CA3AF]">판정 사유</p>
                <div className="rounded bg-[#1F2937] p-3 font-mono text-xs text-[#F3F4F6] whitespace-pre-wrap">
                  {eventDetail.reason || "-"}
                </div>
              </div>
              {eventDetail.matched_patterns && (
                <div>
                  <p className="mb-1 text-xs font-semibold text-[#9CA3AF]">매칭된 패턴</p>
                  <div className="rounded bg-[#1F2937] p-3 font-mono text-xs text-[#F3F4F6] whitespace-pre-wrap">
                    {eventDetail.matched_patterns}
                  </div>
                </div>
              )}
              {eventDetail.llm_raw_response && (
                <div>
                  <p className="mb-1 text-xs font-semibold text-[#9CA3AF]">LLM 원본 응답</p>
                  <div className="rounded bg-[#1F2937] p-3 font-mono text-xs text-[#F3F4F6] whitespace-pre-wrap">
                    {eventDetail.llm_raw_response}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-4">
      <span className="w-28 shrink-0 text-xs font-semibold text-[#9CA3AF]">{label}</span>
      <span className="text-sm text-[#F3F4F6]">{value}</span>
    </div>
  )
}
