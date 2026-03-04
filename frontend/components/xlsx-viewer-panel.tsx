"use client";

import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";
import { useXlsxViewerSelector } from "@/hooks/use-xlsx-viewer";

const SpreadsheetViewer = dynamic(
  () =>
    import("./spreadsheet-viewer").then((mod) => ({
      default: mod.SpreadsheetViewer,
    })),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center bg-background">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="text-sm">뷰어 로딩 중...</span>
        </div>
      </div>
    ),
  }
);

export function XlsxViewerPanel() {
  const isOpen = useXlsxViewerSelector((state) => state.isOpen);

  if (!isOpen) return null;

  return <SpreadsheetViewer />;
}
