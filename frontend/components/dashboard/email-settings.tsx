"use client"

import { useState, useEffect, useCallback } from "react"
import {
  Mail, Plus, Trash2, Send, Eye, Loader2, CheckCircle, XCircle, Clock,
  Settings, Users, History,
} from "lucide-react"
import { SectionHeader } from "./section-header"
import {
  emailApi,
  type EmailConfig,
  type EmailHistory,
  type EmailRecipient,
} from "@/lib/api/report"
import { getApiUrl } from "@/lib/api/config"

const DAY_OPTIONS = [
  { value: "mon", label: "월요일" },
  { value: "tue", label: "화요일" },
  { value: "wed", label: "수요일" },
  { value: "thu", label: "목요일" },
  { value: "fri", label: "금요일" },
  { value: "sat", label: "토요일" },
  { value: "sun", label: "일요일" },
]

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => ({
  value: i,
  label: `${String(i).padStart(2, "0")}시`,
}))

const STATUS_BADGE: Record<string, { color: string; text: string }> = {
  success: { color: "text-[#10B981] bg-[#10B981]/10", text: "성공" },
  partial: { color: "text-[#F59E0B] bg-[#F59E0B]/10", text: "부분 성공" },
  failed: { color: "text-[#EF4444] bg-[#EF4444]/10", text: "실패" },
}

export function EmailSettings() {
  const [config, setConfig] = useState<EmailConfig | null>(null)
  const [history, setHistory] = useState<EmailHistory[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [sending, setSending] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)

  // 수신자 추가 폼
  const [newEmail, setNewEmail] = useState("")
  const [newName, setNewName] = useState("")

  const loadData = useCallback(async () => {
    try {
      const [cfg, hist] = await Promise.all([
        emailApi.getConfig(),
        emailApi.getHistory(10),
      ])
      setConfig(cfg)
      setHistory(hist)
    } catch (e) {
      setMessage({ type: "error", text: "설정을 불러오는 중 오류가 발생했습니다" })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const showMessage = (type: "success" | "error", text: string) => {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 4000)
  }

  // ─── 설정 업데이트 ───

  const updateConfig = async (updates: Partial<EmailConfig>) => {
    setSaving(true)
    try {
      await emailApi.updateConfig(updates)
      setConfig(prev => prev ? { ...prev, ...updates } : prev)
      showMessage("success", "설정이 저장되었습니다")
    } catch {
      showMessage("error", "설정 저장 실패")
    } finally {
      setSaving(false)
    }
  }

  // ─── 수신자 관리 ───

  const addRecipient = async () => {
    if (!newEmail || !newEmail.includes("@")) {
      showMessage("error", "유효한 이메일을 입력해주세요")
      return
    }
    try {
      const result = await emailApi.addRecipient(newEmail, newName)
      if (result.success) {
        setNewEmail("")
        setNewName("")
        await loadData()
        showMessage("success", result.message)
      } else {
        showMessage("error", result.message)
      }
    } catch {
      showMessage("error", "수신자 추가 실패")
    }
  }

  const removeRecipient = async (email: string) => {
    try {
      const result = await emailApi.removeRecipient(email)
      if (result.success) {
        await loadData()
        showMessage("success", result.message)
      } else {
        showMessage("error", result.message)
      }
    } catch {
      showMessage("error", "수신자 삭제 실패")
    }
  }

  // ─── 액션 ───

  const handlePreview = async () => {
    setPreviewing(true)
    try {
      const result = await emailApi.preview()
      if (result.success) {
        window.open(`${getApiUrl()}${result.downloadUrl}`, "_blank")
      }
    } catch {
      showMessage("error", "미리보기 생성 실패")
    } finally {
      setPreviewing(false)
    }
  }

  const handleSendNow = async () => {
    if (!confirm("지금 즉시 주간 리포트를 발송하시겠습니까?")) return
    setSending(true)
    try {
      const result = await emailApi.sendNow()
      if (result.success) {
        showMessage("success", `${result.sent_count}명에게 발송 완료`)
        await loadData()
      } else {
        showMessage("error", result.message)
      }
    } catch {
      showMessage("error", "발송 실패")
    } finally {
      setSending(false)
    }
  }

  if (loading) {
    return (
      <section>
        <SectionHeader title="주간 리포트 이메일" subtitle="Weekly Report Email" />
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-[#3B82F6]" />
          <span className="ml-2 text-sm text-[#9CA3AF]">설정 로드 중...</span>
        </div>
      </section>
    )
  }

  if (!config) return null

  return (
    <section>
      <SectionHeader title="주간 리포트 이메일" subtitle="Weekly Report Email" />

      {/* 알림 메시지 */}
      {message && (
        <div className={`mb-4 flex items-center gap-2 rounded-lg px-4 py-3 text-sm ${
          message.type === "success"
            ? "border border-[#10B981]/30 bg-[#10B981]/10 text-[#10B981]"
            : "border border-[#EF4444]/30 bg-[#EF4444]/10 text-[#EF4444]"
        }`}>
          {message.type === "success" ? <CheckCircle className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
          {message.text}
        </div>
      )}

      <div className="rounded-xl border border-[#334155] bg-[#1F2937]/50 p-6">

        {/* ─── 토글 + SMTP 상태 ─── */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Settings className="h-5 w-5 text-[#3B82F6]" />
            <span className="text-sm font-medium text-[#F3F4F6]">자동 발송</span>
            <button
              onClick={() => updateConfig({ enabled: !config.enabled })}
              disabled={saving}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                config.enabled ? "bg-[#3B82F6]" : "bg-[#334155]"
              }`}
            >
              <span className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                config.enabled ? "translate-x-6" : "translate-x-1"
              }`} />
            </button>
          </div>
          <div className="flex items-center gap-2">
            <div className={`h-2 w-2 rounded-full ${config.smtpConnected ? "bg-[#10B981]" : "bg-[#EF4444]"}`} />
            <span className="text-xs text-[#9CA3AF]">
              SMTP {config.smtpConnected ? "연결됨" : "연결 안됨"}
            </span>
          </div>
        </div>

        {/* ─── 스케줄 설정 ─── */}
        <div className="mb-6 flex items-center gap-4">
          <Clock className="h-4 w-4 text-[#9CA3AF]" />
          <span className="text-sm text-[#9CA3AF]">발송 스케줄:</span>
          <select
            value={config.send_day}
            onChange={(e) => updateConfig({ send_day: e.target.value })}
            className="rounded-lg border border-[#334155] bg-[#0F172A] px-3 py-1.5 text-sm text-[#F3F4F6] focus:border-[#3B82F6] focus:outline-none"
          >
            {DAY_OPTIONS.map(d => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </select>
          <select
            value={config.send_hour}
            onChange={(e) => updateConfig({ send_hour: parseInt(e.target.value) })}
            className="rounded-lg border border-[#334155] bg-[#0F172A] px-3 py-1.5 text-sm text-[#F3F4F6] focus:border-[#3B82F6] focus:outline-none"
          >
            {HOUR_OPTIONS.map(h => (
              <option key={h.value} value={h.value}>{h.label}</option>
            ))}
          </select>
        </div>

        {/* ─── 수신자 목록 ─── */}
        <div className="mb-6">
          <div className="mb-3 flex items-center gap-2">
            <Users className="h-4 w-4 text-[#9CA3AF]" />
            <span className="text-sm font-medium text-[#F3F4F6]">
              수신자 목록 ({config.recipients.length}명)
            </span>
          </div>

          {/* 수신자 테이블 */}
          {config.recipients.length > 0 && (
            <div className="mb-3 rounded-lg border border-[#334155]/50 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[#0F172A]/50">
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-[#9CA3AF]">이름</th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-[#9CA3AF]">이메일</th>
                    <th className="px-4 py-2 text-right text-xs font-medium uppercase text-[#9CA3AF]">삭제</th>
                  </tr>
                </thead>
                <tbody>
                  {config.recipients.map((r: EmailRecipient) => (
                    <tr key={r.email} className="border-t border-[#334155]/30 hover:bg-[#334155]/20">
                      <td className="px-4 py-2 text-[#F3F4F6]">{r.name || "-"}</td>
                      <td className="px-4 py-2 font-mono text-[#3B82F6]">{r.email}</td>
                      <td className="px-4 py-2 text-right">
                        <button
                          onClick={() => removeRecipient(r.email)}
                          className="rounded p-1 text-[#EF4444]/60 hover:bg-[#EF4444]/10 hover:text-[#EF4444]"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* 수신자 추가 폼 */}
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="이름"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="w-28 rounded-lg border border-[#334155] bg-[#0F172A] px-3 py-1.5 text-sm text-[#F3F4F6] placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
            />
            <input
              type="email"
              placeholder="이메일 주소"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addRecipient()}
              className="flex-1 rounded-lg border border-[#334155] bg-[#0F172A] px-3 py-1.5 text-sm text-[#F3F4F6] placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
            />
            <button
              onClick={addRecipient}
              className="flex items-center gap-1.5 rounded-lg bg-[#3B82F6] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#2563EB] transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              추가
            </button>
          </div>
        </div>

        {/* ─── 액션 버튼 ─── */}
        <div className="mb-6 flex items-center gap-3">
          <button
            onClick={handlePreview}
            disabled={previewing}
            className="flex items-center gap-2 rounded-lg border border-[#334155] bg-[#0F172A] px-4 py-2 text-sm text-[#F3F4F6] hover:border-[#3B82F6] hover:text-[#3B82F6] transition-colors disabled:opacity-50"
          >
            {previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
            PDF 미리보기
          </button>
          <button
            onClick={handleSendNow}
            disabled={sending || config.recipients.length === 0}
            className="flex items-center gap-2 rounded-lg bg-[#10B981] px-4 py-2 text-sm font-medium text-white hover:bg-[#059669] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            지금 발송
          </button>
        </div>

        {/* ─── 발송 이력 ─── */}
        {history.length > 0 && (
          <div>
            <div className="mb-3 flex items-center gap-2">
              <History className="h-4 w-4 text-[#9CA3AF]" />
              <span className="text-sm font-medium text-[#F3F4F6]">최근 발송 이력</span>
            </div>
            <div className="rounded-lg border border-[#334155]/50 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[#0F172A]/50">
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-[#9CA3AF]">발송 일시</th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-[#9CA3AF]">기간</th>
                    <th className="px-4 py-2 text-center text-xs font-medium uppercase text-[#9CA3AF]">수신자</th>
                    <th className="px-4 py-2 text-center text-xs font-medium uppercase text-[#9CA3AF]">상태</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h) => {
                    const badge = STATUS_BADGE[h.status] || STATUS_BADGE.failed
                    return (
                      <tr key={h.id} className="border-t border-[#334155]/30 hover:bg-[#334155]/20">
                        <td className="px-4 py-2 font-mono text-[#F3F4F6]">{h.sentAt}</td>
                        <td className="px-4 py-2 text-[#9CA3AF]">{h.dateFrom} ~ {h.dateTo}</td>
                        <td className="px-4 py-2 text-center text-[#F3F4F6]">{h.recipientCount}명</td>
                        <td className="px-4 py-2 text-center">
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${badge.color}`}>
                            {badge.text}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </section>
  )
}
