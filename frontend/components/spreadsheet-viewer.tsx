"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import { X, FileDown, Loader2 } from "lucide-react";
import { useXlsxViewer } from "@/hooks/use-xlsx-viewer";
import "@univerjs/presets/lib/styles/preset-sheets-core.css";

export function SpreadsheetViewer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const univerRef = useRef<any>(null);
  const innerRef = useRef<HTMLDivElement | null>(null);
  const { state, closeViewer, setLoading } = useXlsxViewer();
  const { resolvedTheme } = useTheme();

  // Dispose Univer on unmount
  useEffect(() => {
    return () => {
      if (univerRef.current) {
        try {
          univerRef.current.dispose();
        } catch {
          // ignore dispose errors
        }
        univerRef.current = null;
      }
      innerRef.current = null;
    };
  }, []);

  // Dark mode sync
  useEffect(() => {
    if (!univerRef.current) return;
    try {
      univerRef.current.setTheme(resolvedTheme === "dark" ? "dark" : "light");
    } catch {
      // setTheme may not be available in all versions
    }
  }, [resolvedTheme]);

  // Fetch and load xlsx when filename or refreshCounter changes.
  useEffect(() => {
    if (!state.filename || !containerRef.current) return;

    let cancelled = false;
    const container = containerRef.current;

    const loadFile = async () => {
      setLoading(true);

      try {
        // --- 1. Fetch xlsx file ---
        const res = await fetch(
          `/api/v1/xlsx/download/${encodeURIComponent(state.filename!)}`
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        if (cancelled) return;

        const buffer = await res.arrayBuffer();
        if (cancelled) return;

        // --- 2. Parse with SheetJS ---
        const XLSX = await import("xlsx");
        const { sheetJsToUniverData } = await import("@/lib/xlsx-to-univer");

        const wb = XLSX.read(new Uint8Array(buffer), { type: "array" });
        const univerData = sheetJsToUniverData(wb);

        if (cancelled) return;

        // --- 3. Dispose old Univer instance ---
        if (univerRef.current) {
          try {
            univerRef.current.dispose();
          } catch {
            // ignore
          }
          univerRef.current = null;
        }

        // Remove the old intermediary div (Univer operated on this, not the React container)
        if (innerRef.current && innerRef.current.parentNode === container) {
          container.removeChild(innerRef.current);
        }
        innerRef.current = null;

        if (cancelled) return;

        // --- 4. Create a fresh intermediary div ---
        // Univer will manipulate this div's children, isolating it from React's DOM
        const innerDiv = document.createElement("div");
        innerDiv.style.width = "100%";
        innerDiv.style.height = "100%";
        container.appendChild(innerDiv);
        innerRef.current = innerDiv;

        // --- 5. Create fresh Univer instance ---
        const { createUniver, LocaleType, mergeLocales } = await import(
          "@univerjs/presets"
        );
        const { UniverSheetsCorePreset } = await import(
          "@univerjs/preset-sheets-core"
        );

        let localeData: any;
        let localeType = LocaleType.KO_KR;
        try {
          const koLocale = await import(
            "@univerjs/preset-sheets-core/locales/ko-KR"
          );
          localeData = koLocale.default;
        } catch {
          const enLocale = await import(
            "@univerjs/preset-sheets-core/locales/en-US"
          );
          localeData = enLocale.default;
          localeType = LocaleType.EN_US;
        }

        if (cancelled) return;

        const { univerAPI } = createUniver({
          locale: localeType,
          locales: {
            [localeType]: mergeLocales(localeData),
          },
          presets: [
            UniverSheetsCorePreset({
              container: innerDiv,
              toolbar: false,
              contextMenu: false,
              formula: {
                initialFormulaComputing: 0,
              },
            }),
          ],
        });

        univerRef.current = univerAPI;
        const api = univerAPI as any;

        // Apply dark mode
        try {
          api.setTheme(resolvedTheme === "dark" ? "dark" : "light");
        } catch {
          // setTheme may not be available
        }

        // --- 6. Create workbook with data (read-only) ---
        api.createWorkbook(univerData);

        // Read-only: try every available Univer API
        try {
          const fWorkbook = api.getActiveWorkbook();
          if (fWorkbook) {
            // Method 1: New permission API (async)
            try {
              const wp = fWorkbook.getWorkbookPermission?.();
              if (wp?.setReadOnly) await wp.setReadOnly();
            } catch { /* not available */ }

            // Method 2: setEditable
            try { fWorkbook.setEditable?.(false); } catch {}

            // Method 3: Old permission API
            try {
              const p = fWorkbook.getPermission?.();
              const uid = fWorkbook.getId?.();
              if (p && uid) p.setWorkbookEditPermission?.(uid, false);
            } catch {}
          }
        } catch {
          // permission API not available
        }

        // Trigger manual recalculation via official Facade API
        setTimeout(() => {
          if (cancelled || !univerRef.current) return;
          try {
            const formulaEngine = univerRef.current.getFormula();
            if (formulaEngine) {
              formulaEngine.executeCalculation();
            }
          } catch (e) {
            console.warn("[SpreadsheetViewer] Formula recalc trigger failed:", e);
          }
        }, 500);

        if (!cancelled) setLoading(false);
      } catch (error) {
        console.error("[SpreadsheetViewer] Failed to load xlsx:", error);
        if (!cancelled) setLoading(false);
      }
    };

    loadFile();

    return () => {
      cancelled = true;
    };
  }, [state.filename, state.refreshCounter, setLoading, resolvedTheme]);

  const downloadUrl = state.filename
    ? `/api/v1/xlsx/download/${encodeURIComponent(state.filename)}`
    : "#";

  return (
    <div className="flex h-full flex-col bg-background border-l">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2 min-h-[44px]">
        <span className="truncate text-sm font-medium text-foreground max-w-[200px]">
          {state.filename || "스프레드시트"}
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

      {/* Univer container */}
      <div ref={containerRef} className="flex-1 relative" />
    </div>
  );
}
