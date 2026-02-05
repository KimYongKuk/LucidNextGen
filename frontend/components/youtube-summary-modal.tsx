"use client";

import { YoutubeSummary } from "@/lib/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ExternalLink, Lightbulb, FileText, Clock } from "lucide-react";

interface YoutubeSummaryModalProps {
  summary: YoutubeSummary;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function YoutubeSummaryModal({
  summary,
  open,
  onOpenChange,
}: YoutubeSummaryModalProps) {
  // 타임스탬프를 클릭하면 유튜브 링크로 이동 (t=초 파라미터 추가)
  const goToTimestamp = (seconds: number) => {
    const url = `${summary.original_link}${
      summary.original_link.includes("?") ? "&" : "?"
    }t=${seconds}`;
    window.open(url, "_blank", "noopener,noreferrer");
  };

  // 시간을 MM:SS 형식으로 변환
  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs
      .toString()
      .padStart(2, "0")}`;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-start gap-2 text-xl font-bold pr-8">
            <span className="flex-1">{summary.title}</span>
            <a
              href={summary.original_link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-800 transition-colors flex-shrink-0"
              title="유튜브에서 보기"
            >
              <ExternalLink className="w-5 h-5" />
            </a>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6 mt-4">
          {/* Keywords */}
          {summary.keywords && summary.keywords.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {summary.keywords.map((keyword, index) => (
                <span
                  key={index}
                  className="px-3 py-1 bg-blue-50 text-blue-700 text-sm rounded-full border border-blue-200"
                >
                  #{keyword}
                </span>
              ))}
            </div>
          )}

          {/* Key Insight */}
          {summary.insight && (
            <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded-r-lg">
              <div className="flex items-start gap-3">
                <Lightbulb className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-amber-900 mb-2">
                    Key Insight
                  </h3>
                  <p className="text-amber-800 text-sm leading-relaxed">
                    {summary.insight}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Summary */}
          <div className="bg-gray-50 border border-gray-200 p-4 rounded-lg">
            <div className="flex items-start gap-3">
              <FileText className="w-5 h-5 text-gray-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-semibold text-gray-900 mb-2">SUMMARY</h3>
                <p className="text-gray-700 text-sm leading-relaxed whitespace-pre-wrap">
                  {summary.summary}
                </p>
              </div>
            </div>
          </div>

          {/* Video Segments */}
          {summary.segments && summary.segments.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-4">
                <Clock className="w-5 h-5 text-gray-600" />
                <h3 className="font-semibold text-gray-900">VIDEO SEGMENTS</h3>
              </div>
              <div className="space-y-3">
                {summary.segments.map((segment, index) => (
                  <div
                    key={index}
                    className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-start gap-3">
                      <button
                        onClick={() => goToTimestamp(segment.start_time)}
                        className="flex-shrink-0 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm font-mono transition-colors"
                        title="유튜브에서 이 시점으로 이동"
                      >
                        {formatTime(segment.start_time)}
                      </button>
                      <div className="flex-1 min-w-0">
                        <h4 className="font-semibold text-gray-900 mb-1">
                          {segment.title}
                        </h4>
                        <p className="text-gray-600 text-sm leading-relaxed">
                          {segment.content}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
