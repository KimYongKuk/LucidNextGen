"use client"

import { useState, useCallback, useEffect } from "react"
import { RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"

const presets = [
  { label: "오늘", value: "today" },
  { label: "최근 7일", value: "7d" },
  { label: "최근 30일", value: "30d" },
] as const

function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}

function calcRange(preset: string): { from: string; to: string } {
  const today = new Date()
  const to = formatDate(today)
  if (preset === "today") return { from: to, to }
  if (preset === "30d") {
    const d = new Date(today)
    d.setDate(d.getDate() - 29)
    return { from: formatDate(d), to }
  }
  // default 7d
  const d = new Date(today)
  d.setDate(d.getDate() - 6)
  return { from: formatDate(d), to }
}

interface Props {
  onRangeChange?: (dateFrom: string, dateTo: string) => void
}

export function DateRangeSelector({ onRangeChange }: Props) {
  const [selected, setSelected] = useState<string>("7d")
  const initRange = calcRange("7d")
  const [startDate, setStartDate] = useState(initRange.from)
  const [endDate, setEndDate] = useState(initRange.to)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const notify = useCallback((from: string, to: string) => {
    onRangeChange?.(from, to)
  }, [onRangeChange])

  useEffect(() => {
    notify(startDate, endDate)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handlePreset(preset: string) {
    setSelected(preset)
    const { from, to } = calcRange(preset)
    setStartDate(from)
    setEndDate(to)
    notify(from, to)
  }

  function handleStartChange(v: string) {
    setStartDate(v)
    setSelected("")
    notify(v, endDate)
  }

  function handleEndChange(v: string) {
    setEndDate(v)
    setSelected("")
    notify(startDate, v)
  }

  function handleRefresh() {
    setIsRefreshing(true)
    notify(startDate, endDate)
    setTimeout(() => setIsRefreshing(false), 800)
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-1.5 rounded-lg border border-[#334155] bg-[#1F2937]/60 p-1">
        {presets.map((p) => (
          <button
            key={p.value}
            onClick={() => handlePreset(p.value)}
            className={cn(
              "rounded-md px-3.5 py-1.5 text-sm font-medium transition-all",
              selected === p.value
                ? "bg-[#3B82F6] text-[#F3F4F6] shadow-sm"
                : "text-[#9CA3AF] hover:text-[#F3F4F6] hover:bg-[#334155]/50"
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <input
          type="date"
          value={startDate}
          onChange={(e) => handleStartChange(e.target.value)}
          className="h-8 rounded-md border border-[#334155] bg-[#1F2937]/60 px-2.5 text-sm text-[#F3F4F6] outline-none focus:border-[#3B82F6] [&::-webkit-calendar-picker-indicator]:invert"
        />
        <span className="text-xs text-[#9CA3AF]">~</span>
        <input
          type="date"
          value={endDate}
          onChange={(e) => handleEndChange(e.target.value)}
          className="h-8 rounded-md border border-[#334155] bg-[#1F2937]/60 px-2.5 text-sm text-[#F3F4F6] outline-none focus:border-[#3B82F6] [&::-webkit-calendar-picker-indicator]:invert"
        />
      </div>

      <button
        onClick={handleRefresh}
        className="flex h-8 w-8 items-center justify-center rounded-md border border-[#334155] bg-[#1F2937]/60 text-[#9CA3AF] transition-colors hover:border-[#3B82F6] hover:text-[#3B82F6]"
        aria-label="새로고침"
      >
        <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
      </button>
    </div>
  )
}
