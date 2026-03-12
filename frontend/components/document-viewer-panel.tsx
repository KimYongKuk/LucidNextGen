"use client";

import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";
import { useDocumentViewerSelector } from "@/hooks/use-document-viewer";

const PdfViewer = dynamic(
  () => import("./pdf-viewer").then((mod) => ({ default: mod.PdfViewer })),
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

const DocxViewer = dynamic(
  () => import("./docx-viewer").then((mod) => ({ default: mod.DocxViewer })),
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

export function DocumentViewerPanel() {
  const isOpen = useDocumentViewerSelector((state) => state.isOpen);
  const documentType = useDocumentViewerSelector(
    (state) => state.documentType
  );

  if (!isOpen) return null;

  if (documentType === "pdf") return <PdfViewer />;
  if (documentType === "docx") return <DocxViewer />;

  return null;
}
