"use client";

import { X, FileDown } from "lucide-react";
import { useDocumentViewer } from "@/hooks/use-document-viewer";

export function PdfViewer() {
  const { state, closeViewer } = useDocumentViewer();

  const downloadUrl = state.filename
    ? `/api/v1/pdf/download/${encodeURIComponent(state.filename)}`
    : "#";

  // iframe용: inline=true로 브라우저 내장 PDF 뷰어 표시
  const previewUrl = state.filename
    ? `/api/v1/pdf/download/${encodeURIComponent(state.filename)}?inline=true`
    : "";

  return (
    <div className="flex h-full flex-col bg-background border-l">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2 min-h-[44px]">
        <span className="truncate text-sm font-medium text-foreground max-w-[200px]">
          {state.filename || "PDF"}
        </span>
        <div className="flex items-center gap-1">
          {state.filename && (
            <a
              href={downloadUrl}
              download={state.filename}
              className="inline-flex items-center justify-center rounded-md p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              title="다운로드"
            >
              <FileDown className="w-4 h-4" />
            </a>
          )}
          <button
            onClick={closeViewer}
            className="inline-flex items-center justify-center rounded-md p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            title="닫기"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* PDF iframe */}
      <div className="flex-1 relative">
        {previewUrl && (
          <iframe
            src={previewUrl}
            className="w-full h-full border-0"
            title={state.filename || "PDF"}
          />
        )}
      </div>
    </div>
  );
}
