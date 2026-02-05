"use client";

import { CorpSource } from "@/lib/types";
import { FileText } from "lucide-react";

interface CorpSourcesCarouselProps {
  sources: CorpSource[];
}

export function CorpSourcesCarousel({ sources }: CorpSourcesCarouselProps) {
  if (!sources || sources.length === 0) {
    return null;
  }

  // 카테고리 이모지 매핑
  const categoryEmoji: Record<string, string> = {
    "인사": "👥",
    "재경": "💰",
    "IT": "💻",
    "공통": "📋",
    "안전환경": "🛡️",
  };

  return (
    <div className="mt-4 border-t border-border pt-4">
      <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
        <FileText className="w-4 h-4" />
        참조 사내 문서
      </h4>
      <div className="space-y-2">
        {sources.map((source, index) => (
          <div
            key={`${source.filename}-${index}`}
            className="flex flex-wrap items-center gap-2 text-sm bg-muted/50 rounded-md px-3 py-2"
          >
            {/* 번호 배지 */}
            <span className="flex items-center justify-center w-6 h-6 bg-primary/10 text-primary rounded-full text-xs font-semibold shrink-0">
              {index + 1}
            </span>

            {/* 카테고리 이모지 */}
            <span className="text-base shrink-0">
              {categoryEmoji[source.category] || "📄"}
            </span>

            {/* 파일명 - 전체 표시 */}
            <span className="text-foreground font-medium">
              {source.filename}
            </span>

            {/* 카테고리 */}
            <span className="ml-auto px-2 py-0.5 bg-primary/5 rounded text-xs text-muted-foreground">
              {source.category}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
