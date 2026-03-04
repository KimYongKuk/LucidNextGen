"use client"

import { Upload, ImageIcon, FileText, Sheet, Presentation } from "lucide-react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts"
import { KpiCard } from "./kpi-card"
import { SectionHeader } from "./section-header"
import type { ArtifactsData } from "@/lib/api/report"

interface Props {
  data: ArtifactsData
}

export function FilesGenerated({ data }: Props) {
  return (
    <section>
      <SectionHeader title="파일 & 생성물" subtitle="Files & Generated Content" />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <KpiCard label="파일 업로드 세션" value={data.fileUploads} icon={Upload} accent="blue" />
        <KpiCard label="이미지 업로드 세션" value={data.imageUploads} icon={ImageIcon} accent="green" />
        <KpiCard label="PDF 생성" value={data.pdfCount} icon={FileText} accent="orange" />
        <KpiCard label="XLSX 생성" value={data.xlsxCount} icon={Sheet} accent="purple" />
        <KpiCard label="PPT 생성" value={data.pptCount} icon={Presentation} accent="default" />
      </div>

      <div className="mt-6 rounded-xl border border-[#334155] bg-[#1F2937]/50 p-5">
        <h3 className="mb-4 text-sm font-medium text-[#9CA3AF]">일별 PDF / XLSX / PPT 생성 추이</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data.dailyTrend} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} />
            <YAxis tick={{ fill: "#9CA3AF", fontSize: 12 }} axisLine={{ stroke: "#334155" }} tickLine={false} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #334155", borderRadius: "8px", color: "#F3F4F6" }}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "#9CA3AF" }} />
            <Bar dataKey="pdf" name="PDF" stackId="a" fill="#F59E0B" radius={[0, 0, 0, 0]} />
            <Bar dataKey="xlsx" name="XLSX" stackId="a" fill="#8B5CF6" radius={[0, 0, 0, 0]} />
            <Bar dataKey="ppt" name="PPT" stackId="a" fill="#3B82F6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
