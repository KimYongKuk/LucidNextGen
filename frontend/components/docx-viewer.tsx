"use client";

import { useEffect, useRef } from "react";
import { X, FileDown, Loader2 } from "lucide-react";
import { useDocumentViewer } from "@/hooks/use-document-viewer";

export function DocxViewer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { state, closeViewer, setLoading } = useDocumentViewer();

  useEffect(() => {
    if (!state.filename || !containerRef.current) return;

    let cancelled = false;
    const container = containerRef.current;

    const loadFile = async () => {
      setLoading(true);

      try {
        // 1. Fetch docx file
        const res = await fetch(
          `/api/v1/docx/download/${encodeURIComponent(state.filename!)}`
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        if (cancelled) return;

        const blob = await res.blob();
        if (cancelled) return;

        // 2. Render with docx-preview
        const docxPreview = await import("docx-preview");

        // Clear previous content
        container.innerHTML = "";

        await docxPreview.renderAsync(blob, container, undefined, {
          className: "docx-preview-wrapper",
          inWrapper: true,
          ignoreWidth: true,
          ignoreHeight: true,
          ignoreFonts: false,
          breakPages: true,
          ignoreLastRenderedPageBreak: true,
          experimental: false,
          trimXmlDeclaration: true,
          useBase64URL: true,
          renderHeaders: true,
          renderFooters: true,
          renderFootnotes: true,
          renderEndnotes: true,
        });

        if (!cancelled) setLoading(false);
      } catch (error) {
        console.error("[DocxViewer] Failed to load docx:", error);
        if (!cancelled) {
          container.innerHTML =
            '<div class="flex items-center justify-center h-full text-muted-foreground text-sm">문서를 불러올 수 없습니다.</div>';
          setLoading(false);
        }
      }
    };

    loadFile();

    return () => {
      cancelled = true;
    };
  }, [state.filename, setLoading]);

  const downloadUrl = state.filename
    ? `/api/v1/docx/download/${encodeURIComponent(state.filename)}`
    : "#";

  return (
    <div className="flex h-full flex-col bg-background border-l">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2 min-h-[44px]">
        <span className="truncate text-sm font-medium text-foreground max-w-[200px]">
          {state.filename || "문서"}
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

      {/* Loading overlay */}
      {state.isLoading && (
        <div className="absolute inset-0 top-[44px] z-10 flex items-center justify-center bg-background/80">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="text-sm">불러오는 중...</span>
          </div>
        </div>
      )}

      {/* DOCX container */}
      <div
        ref={containerRef}
        className="flex-1 relative overflow-y-auto overflow-x-hidden bg-gray-100 dark:bg-zinc-900"
      />
    </div>
  );
}
