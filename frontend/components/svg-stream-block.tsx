'use client';

import { useState, useCallback, useRef, useEffect, memo } from 'react';
import { Download, Maximize2, Minimize2, MoreHorizontal, Copy, Check } from 'lucide-react';

interface SVGStreamBlockProps {
  svgContent: string;
  isStreaming?: boolean;
}

/**
 * 인라인 SVG 스트리밍 렌더링 블록
 *
 * DOMPurify 정제 후 div에 직접 렌더링 (iframe 제거 — 로드 타이밍/배경 이슈 해결)
 * 내부 SVG div를 memo로 감싸서 불필요한 DOM 재생성 방지
 */

// SVG 렌더링 영역 (memo로 불필요한 리렌더 방지)
const SvgRenderer = memo(({ html }: { html: string }) => (
  <div
    className="w-full [&>svg]:w-full [&>svg]:h-auto [&>svg]:block"
    dangerouslySetInnerHTML={{ __html: html }}
  />
));
SvgRenderer.displayName = 'SvgRenderer';

export function SVGStreamBlock({ svgContent, isStreaming = false }: SVGStreamBlockProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [sanitizedSvg, setSanitizedSvg] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);

  // DOMPurify 동적 로드 + SVG 정제 (SSR 안전)
  useEffect(() => {
    if (!svgContent) { setSanitizedSvg(''); return; }

    import('dompurify').then((mod) => {
      const DOMPurify = mod.default || mod;

      const clean = DOMPurify.sanitize(svgContent, {
        USE_PROFILES: { svg: true, svgFilters: true },
        ADD_TAGS: [
          'filter', 'feDropShadow', 'feGaussianBlur', 'feOffset',
          'feMerge', 'feMergeNode', 'feFlood', 'feComposite', 'feColorMatrix',
          'linearGradient', 'radialGradient', 'stop', 'defs', 'clipPath', 'pattern',
          'marker', 'mask', 'use', 'symbol', 'textPath', 'style',
        ],
        ADD_ATTR: [
          'viewBox', 'xmlns', 'fill', 'stroke', 'stroke-width', 'stroke-dasharray',
          'stroke-linecap', 'stroke-linejoin', 'rx', 'ry', 'cx', 'cy', 'r',
          'x', 'y', 'x1', 'y1', 'x2', 'y2', 'dx', 'dy', 'd', 'points',
          'transform', 'text-anchor', 'dominant-baseline', 'font-family',
          'font-size', 'font-weight', 'opacity', 'fill-opacity', 'stroke-opacity',
          'filter', 'clip-path', 'marker-end', 'marker-start',
          'stdDeviation', 'in', 'flood-color', 'flood-opacity', 'result', 'operator',
          'offset', 'stop-color', 'stop-opacity', 'gradientUnits', 'gradientTransform',
          'patternUnits', 'patternTransform', 'preserveAspectRatio',
          'href', 'xlink:href', 'letter-spacing', 'word-spacing', 'text-decoration',
        ],
      });

      // width/height 제거 + overflow visible
      let responsive = clean
        .replace(/(<svg[^>]*?)\s+width\s*=\s*["'][^"']*["']/i, '$1')
        .replace(/(<svg[^>]*?)\s+height\s*=\s*["'][^"']*["']/i, '$1')
        .replace(/(<svg\b)/, '$1 overflow="visible"');


      setSanitizedSvg(responsive);
    });
  }, [svgContent]);

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
      await navigator.clipboard.writeText(svgContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
    setMenuOpen(false);
  }, [svgContent]);

  const handleDownload = useCallback(() => {
    try {
      const svgBlob = new Blob([svgContent], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'visual.svg';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('SVG download failed:', e);
    }
    setMenuOpen(false);
  }, [svgContent]);

  const handleExpand = useCallback(() => {
    setIsExpanded(true);
    setMenuOpen(false);
  }, []);

  if (!sanitizedSvg) return null;

  return (
    <div className="my-4">
      <div
        className={`group/svg relative transition-all duration-200 ${isExpanded ? 'fixed inset-4 z-50 bg-[var(--secondary)] rounded-xl overflow-auto p-4' : ''}`}
      >
        {/* ... 오버레이 메뉴 (hover 시 표시, 스트리밍 중 숨김) */}
        {!isStreaming && (
          <div ref={menuRef} className="absolute top-2 right-2 z-10">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="opacity-0 group-hover/svg:opacity-100 transition-opacity rounded-lg p-1.5 bg-black/50 hover:bg-black/70 text-gray-300 hover:text-white backdrop-blur-sm"
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
                  {copied ? 'Copied!' : 'Copy SVG code'}
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

        {/* SVG 렌더링 */}
        <SvgRenderer html={sanitizedSvg} />
      </div>

      {isExpanded && (
        <div
          className="fixed inset-0 z-40 bg-black/60"
          onClick={() => setIsExpanded(false)}
        />
      )}
    </div>
  );
}
