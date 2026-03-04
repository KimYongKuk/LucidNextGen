import { cn } from "@/lib/utils"
import type { LucideIcon } from "lucide-react"

interface KpiCardProps {
  label: string
  value: string | number
  icon: LucideIcon
  trend?: string
  trendUp?: boolean
  accent?: "blue" | "green" | "orange" | "red" | "purple" | "default"
}

const accentMap = {
  blue: "text-[#3B82F6]",
  green: "text-[#10B981]",
  orange: "text-[#F59E0B]",
  red: "text-[#EF4444]",
  purple: "text-[#8B5CF6]",
  default: "text-[#F3F4F6]",
}

const accentBgMap = {
  blue: "bg-[#3B82F6]/10",
  green: "bg-[#10B981]/10",
  orange: "bg-[#F59E0B]/10",
  red: "bg-[#EF4444]/10",
  purple: "bg-[#8B5CF6]/10",
  default: "bg-[#F3F4F6]/10",
}

export function KpiCard({ label, value, icon: Icon, trend, trendUp, accent = "default" }: KpiCardProps) {
  return (
    <div className="rounded-xl border border-[#334155] bg-[#1F2937]/80 p-5 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium tracking-wide text-[#9CA3AF] uppercase">{label}</span>
        <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg", accentBgMap[accent])}>
          <Icon className={cn("h-4 w-4", accentMap[accent])} />
        </div>
      </div>
      <div className="mt-3">
        <span className={cn("text-3xl font-bold tracking-tight", accentMap[accent === "default" ? "default" : accent])}>
          {typeof value === "number" ? value.toLocaleString() : value}
        </span>
      </div>
      {trend && (
        <p className={cn("mt-1.5 text-xs font-medium", trendUp ? "text-[#10B981]" : "text-[#EF4444]")}>
          {trend}
        </p>
      )}
    </div>
  )
}
