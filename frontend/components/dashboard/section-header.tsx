interface SectionHeaderProps {
  title: string
  subtitle?: string
}

export function SectionHeader({ title, subtitle }: SectionHeaderProps) {
  return (
    <div className="mb-5">
      <h2 className="text-lg font-semibold text-[#F3F4F6]">{title}</h2>
      {subtitle && <p className="mt-0.5 text-sm text-[#9CA3AF]">{subtitle}</p>}
    </div>
  )
}
