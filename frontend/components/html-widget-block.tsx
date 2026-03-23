'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { Download, Maximize2, Minimize2, MoreHorizontal, Copy, Check } from 'lucide-react';
import { useTheme } from 'next-themes';

interface HTMLWidgetBlockProps {
  htmlContent: string;
  isStreaming?: boolean;
}

// iframe shell — CSS 변수 기반 테마 (호스트에서 동적 갱신)
const IFRAME_SHELL = `<!DOCTYPE html><html><head>
<style id="theme-vars">
:root {
  --w-bg: #1e1e1e;
  --w-bg-sub: #2d2d2d;
  --w-text: #E2E8F0;
  --w-text-sub: #94A3B8;
  --w-border: #404040;
  --w-link: #60A5FA;
  --w-accent-blue: #60A5FA;
  --w-accent-green: #34D399;
  --w-accent-red: #F87171;
  --w-accent-yellow: #FBBF24;
  --w-positive: #34D399;
  --w-negative: #F87171;
  --w-card: #2d2d2d;
  --w-badge-bg: #065F46;
  --w-badge-text: #34D399;
  --w-row-alt: #2d2d2d;
}
</style>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{background:var(--w-bg);color:var(--w-text);font-family:'Malgun Gothic','Segoe UI',sans-serif;font-size:14px;line-height:1.6}
body{padding:16px}
table{border-collapse:collapse;width:100%}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--w-border)}
th{color:var(--w-text-sub);font-weight:600;font-size:13px}
a{color:var(--w-link);text-decoration:none}
</style>
</head><body></body></html>`;

// 테마별 CSS 변수 값
const THEME_VARS = {
  dark: `--w-bg:#1e1e1e;--w-bg-sub:#2d2d2d;--w-text:#E2E8F0;--w-text-sub:#94A3B8;--w-border:#404040;--w-link:#60A5FA;--w-accent-blue:#60A5FA;--w-accent-green:#34D399;--w-accent-red:#F87171;--w-accent-yellow:#FBBF24;--w-positive:#34D399;--w-negative:#F87171;--w-card:#2d2d2d;--w-badge-bg:#065F46;--w-badge-text:#34D399;--w-row-alt:#2d2d2d`,
  light: `--w-bg:#ffffff;--w-bg-sub:#F8FAFC;--w-text:#1E293B;--w-text-sub:#64748B;--w-border:#E2E8F0;--w-link:#2563EB;--w-accent-blue:#3B82F6;--w-accent-green:#10B981;--w-accent-red:#EF4444;--w-accent-yellow:#F59E0B;--w-positive:#10B981;--w-negative:#EF4444;--w-card:#F8FAFC;--w-badge-bg:#D1FAE5;--w-badge-text:#065F46;--w-row-alt:#F8FAFC`,
};

/**
 * HTML 위젯 렌더링 블록
 *
 * LLM이 <lucid-html>...</lucid-html>로 감싼 HTML 프래그먼트를 출력하면
 * iframe sandbox 안에서 격리 렌더링합니다.
 *
 * - <style> 격리: 호스트 CSS와 충돌 방지
 * - <script> 허용: 인터랙티브 요소 가능 (sandbox 제한 내)
 * - 스트리밍: contentDocument.body.innerHTML RAF 업데이트
 * - 완성 후: scrollHeight 기반 자동 높이 조절
 */
export function HTMLWidgetBlock({ htmlContent, isStreaming = false }: HTMLWidgetBlockProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme !== 'light';
  const [isExpanded, setIsExpanded] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [iframeHeight, setIframeHeight] = useState(200);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const iframeReadyRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const lastWrittenRef = useRef<string>('');
  const menuRef = useRef<HTMLDivElement>(null);

  // iframe 로드 완료
  const handleIframeLoad = useCallback(() => {
    iframeReadyRef.current = true;
    try {
      const doc = iframeRef.current?.contentDocument;
      if (!doc) return;

      // 현재 테마 즉시 적용
      const styleEl = doc.getElementById('theme-vars');
      if (styleEl) {
        const vars = isDark ? THEME_VARS.dark : THEME_VARS.light;
        styleEl.textContent = `:root { ${vars} }`;
      }

      // 초기 콘텐츠가 이미 있으면 즉시 주입
      if (htmlContent && lastWrittenRef.current !== htmlContent) {
        lastWrittenRef.current = htmlContent;
        if (doc.body) {
          doc.body.innerHTML = htmlContent;
        }
      }
    } catch { /* ignore */ }
  }, [htmlContent, isDark]);

  // 테마 변경 시 iframe 내부 CSS 변수 갱신 (iframe 재로드 없이)
  useEffect(() => {
    try {
      const doc = iframeRef.current?.contentDocument;
      const styleEl = doc?.getElementById('theme-vars');
      if (styleEl) {
        const vars = isDark ? THEME_VARS.dark : THEME_VARS.light;
        styleEl.textContent = `:root { ${vars} }`;
      }
    } catch { /* ignore */ }
  }, [isDark]);

  // 높이 측정 헬퍼
  const adjustHeight = useCallback(() => {
    try {
      const doc = iframeRef.current?.contentDocument;
      if (doc?.body) {
        const h = doc.body.scrollHeight;
        if (h > 0) setIframeHeight(h);
      }
    } catch { /* ignore */ }
  }, []);

  // iframe body에 HTML 주입 + 즉시 높이 갱신 (RAF throttle)
  useEffect(() => {
    if (!htmlContent || !iframeReadyRef.current) return;
    if (htmlContent === lastWrittenRef.current) return;

    lastWrittenRef.current = htmlContent;

    if (rafRef.current) return;

    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      try {
        const doc = iframeRef.current?.contentDocument;
        if (doc?.body) {
          doc.body.innerHTML = lastWrittenRef.current;
          // 주입 직후 높이 갱신
          const h = doc.body.scrollHeight;
          if (h > 0) setIframeHeight(h);
        }
      } catch { /* ignore */ }
    });

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [htmlContent]);

  // 완성 후 최종 높이 조절 (script 실행 후 레이아웃 변경 대응)
  useEffect(() => {
    if (isStreaming) return;
    adjustHeight();
    const timer = setTimeout(adjustHeight, 300);
    return () => clearTimeout(timer);
  }, [isStreaming, adjustHeight]);

  // 메뉴 외부 클릭 닫기
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuOpen]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(htmlContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
    setMenuOpen(false);
  }, [htmlContent]);

  const handleDownload = useCallback(() => {
    try {
      const fullHtml = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#1e1e1e;color:#E2E8F0;font-family:'Malgun Gothic',sans-serif;font-size:14px;line-height:1.6;padding:24px}
table{border-collapse:collapse;width:100%}th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #404040}
th{color:#94A3B8;font-weight:600}a{color:#60A5FA}
</style></head><body>${htmlContent}</body></html>`;
      const blob = new Blob([fullHtml], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'widget.html';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('HTML download failed:', e);
    }
    setMenuOpen(false);
  }, [htmlContent]);

  const handleExpand = useCallback(() => {
    setIsExpanded(true);
    setMenuOpen(false);
  }, []);

  if (!htmlContent) return null;

  return (
    <div className="my-4">
      <div
        className={`group/widget relative transition-all duration-200 ${isExpanded ? 'fixed inset-4 z-50 bg-[#1e1e1e] rounded-xl overflow-auto' : ''}`}
      >
        {/* ... 오버레이 메뉴 (hover 시 표시, 스트리밍 중 숨김) */}
        {!isStreaming && (
          <div ref={menuRef} className="absolute top-2 right-2 z-10">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="opacity-0 group-hover/widget:opacity-100 transition-opacity rounded-lg p-1.5 bg-black/50 hover:bg-black/70 text-gray-300 hover:text-white backdrop-blur-sm"
            >
              <MoreHorizontal size={16} />
            </button>

            {menuOpen && (
              <div className="absolute top-9 right-0 w-44 rounded-lg border border-gray-600 bg-gray-800 shadow-xl py-1 text-sm">
                <button
                  onClick={handleCopy}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
                >
                  {copied ? <Check size={15} className="text-green-400" /> : <Copy size={15} />}
                  {copied ? 'Copied!' : 'Copy HTML code'}
                </button>
                <button
                  onClick={handleDownload}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
                >
                  <Download size={15} />
                  Download file
                </button>
                <button
                  onClick={handleExpand}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
                >
                  <Maximize2 size={15} />
                  Expand
                </button>
              </div>
            )}
          </div>
        )}

        {/* 확대 모드 닫기 버튼 */}
        {isExpanded && (
          <button
            onClick={() => setIsExpanded(false)}
            className="absolute top-3 right-3 z-10 rounded-lg p-2 bg-black/50 hover:bg-black/70 text-gray-300 hover:text-white backdrop-blur-sm transition-colors"
          >
            <Minimize2 size={18} />
          </button>
        )}

        {/* HTML Content — iframe sandbox 격리 */}
        <iframe
          ref={iframeRef}
          srcDoc={IFRAME_SHELL}
          onLoad={handleIframeLoad}
          sandbox="allow-scripts allow-same-origin"
          className="w-full border-0 rounded-lg"
          style={{
            background: isDark ? '#1e1e1e' : '#ffffff',
            height: isExpanded ? '100%' : `${iframeHeight + 8}px`,
            minHeight: '100px',
            transition: isStreaming ? 'none' : 'height 0.3s ease',
          }}
          title="HTML Widget"
        />
      </div>

      {/* Overlay backdrop when expanded */}
      {isExpanded && (
        <div
          className="fixed inset-0 z-40 bg-black/60"
          onClick={() => setIsExpanded(false)}
        />
      )}
    </div>
  );
}