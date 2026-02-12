"use client";

import { useState } from "react";
import { CorpSource } from "@/lib/types";
import { FileText, ChevronDown, ChevronUp } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface CorpSourcesCarouselProps {
  sources: CorpSource[];
}

export function CorpSourcesCarousel({ sources }: CorpSourcesCarouselProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

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

  const hasChunks = (source: CorpSource) =>
    source.chunks && source.chunks.length > 0;

  const toggleExpand = (index: number) => {
    setExpandedIndex((prev) => (prev === index ? null : index));
  };

  return (
    <div className="mt-4 border-t border-border pt-4">
      <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
        <FileText className="w-4 h-4" />
        참조 사내 문서
      </h4>
      <div className="space-y-2">
        {sources.map((source, index) => (
          <div key={`${source.filename}-${index}`}>
            {/* 헤더 행 */}
            <div
              className={`flex flex-wrap items-center gap-2 text-sm bg-muted/50 rounded-md px-3 py-2 ${
                hasChunks(source)
                  ? "cursor-pointer hover:bg-muted/80 transition-colors"
                  : ""
              }`}
              onClick={() => hasChunks(source) && toggleExpand(index)}
            >
              {/* 번호 배지 */}
              <span className="flex items-center justify-center w-6 h-6 bg-primary/10 text-primary rounded-full text-xs font-semibold shrink-0">
                {index + 1}
              </span>

              {/* 카테고리 이모지 */}
              <span className="text-base shrink-0">
                {categoryEmoji[source.category] || "📄"}
              </span>

              {/* 파일명 */}
              <span className="text-foreground font-medium">
                {source.filename}
              </span>

              {/* 유사도 뱃지 */}
              {source.similarity != null && source.similarity > 0 && (
                <span className="px-1.5 py-0.5 bg-green-100 dark:bg-green-900/30 rounded text-xs text-green-700 dark:text-green-400">
                  {(source.similarity * 100).toFixed(0)}%
                </span>
              )}

              {/* 카테고리 */}
              <span className="ml-auto px-2 py-0.5 bg-primary/5 rounded text-xs text-muted-foreground">
                {source.category}
              </span>

              {/* 확장/축소 아이콘 */}
              {hasChunks(source) && (
                <span className="text-muted-foreground">
                  {expandedIndex === index ? (
                    <ChevronUp className="w-4 h-4" />
                  ) : (
                    <ChevronDown className="w-4 h-4" />
                  )}
                </span>
              )}
            </div>

            {/* 청크 내용 펼침 영역 */}
            <AnimatePresence>
              {expandedIndex === index && hasChunks(source) && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="ml-8 mt-1 space-y-2">
                    {source.chunks!.map((chunk, chunkIdx) => (
                      <div
                        key={chunkIdx}
                        className="text-sm bg-muted/30 rounded-md px-3 py-2 border-l-2 border-primary/30"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-medium text-primary/70">
                            청크 {chunkIdx + 1}
                          </span>
                          {chunk.similarity > 0 && (
                            <span className="text-xs text-muted-foreground">
                              유사도: {(chunk.similarity * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                        <p className="whitespace-pre-wrap text-foreground/80 text-xs leading-relaxed">
                          {chunk.text}
                        </p>
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>
    </div>
  );
}
