'use client';

import { useState, useMemo, useRef, useCallback } from 'react';
import { Download, Maximize2, Minimize2 } from 'lucide-react';
import DOMPurify from 'dompurify';

export interface SvgVisualData {
  success: boolean;
  type: 'svg_visual';
  title: string;
  visual_type: 'infographic' | 'flowchart' | 'timeline' | 'comparison' | 'diagram' | 'dashboard' | 'process';
  description?: string;
  svg: string;
}

interface SVGDisplayProps {
  svgData: SvgVisualData;
}

// visual_type 한국어 라벨
const VISUAL_TYPE_LABELS: Record<string, string> = {
  infographic: '인포그래픽',
  flowchart: '플로우차트',
  timeline: '타임라인',
  comparison: '비교',
  diagram: '다이어그램',
  dashboard: '대시보드',
  process: '프로세스',
};

export function SVGDisplay({ svgData }: SVGDisplayProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const { title, visual_type, description, svg } = svgData;

  // DOMPurify로 SVG 정제 후 렌더링
  const sanitizedSvg = useMemo(() => {
    if (!svg) return '';

    // DOMPurify SVG 전용 설정
    const clean = DOMPurify.sanitize(svg, {
      USE_PROFILES: { svg: true, svgFilters: true },
      ADD_TAGS: ['filter', 'feDropShadow', 'feGaussianBlur', 'feOffset', 'feMerge', 'feMergeNode', 'feFlood', 'feComposite', 'feColorMatrix'],
      ADD_ATTR: ['viewBox', 'xmlns', 'fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'rx', 'ry', 'cx', 'cy', 'r', 'x', 'y', 'x1', 'y1', 'x2', 'y2', 'dx', 'dy', 'd', 'points', 'transform', 'text-anchor', 'dominant-baseline', 'font-family', 'font-size', 'font-weight', 'opacity', 'fill-opacity', 'stroke-opacity', 'filter', 'clip-path', 'marker-end', 'marker-start', 'stdDeviation', 'in', 'flood-color', 'flood-opacity', 'result', 'operator'],
    });

    // width/height를 100%로 변환 (반응형)
    let responsive = clean;
    responsive = responsive.replace(
      /(<svg[^>]*?)\s+width\s*=\s*["']\d+(?:px)?["']/i,
      '$1 width="100%"'
    );
    responsive = responsive.replace(
      /(<svg[^>]*?)\s+height\s*=\s*["']\d+(?:px)?["']/i,
      '$1 height="100%"'
    );

    return responsive;
  }, [svg]);

  // SVG 파일 다운로드
  const handleDownload = useCallback(() => {
    try {
      const svgBlob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);

      const link = document.createElement('a');
      link.href = url;
      link.download = `${title.replace(/[^a-zA-Z0-9가-힣\s-]/g, '').trim() || 'visual'}.svg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('SVG download failed:', e);
    }
  }, [svg, title]);

  const typeLabel = VISUAL_TYPE_LABELS[visual_type] || visual_type;

  return (
    <div className="my-4">
      {/* Border line */}
      <div className="mb-4 border-t border-border/50" />

      <div className={`rounded-lg border border-gray-700 bg-gray-800 overflow-hidden transition-all duration-200 ${isExpanded ? 'fixed inset-4 z-50' : ''}`}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 bg-gray-800/80">
          <div className="flex items-center gap-2 min-w-0">
            <span className="inline-flex items-center rounded-md bg-blue-500/10 px-2 py-0.5 text-xs font-medium text-blue-400 ring-1 ring-inset ring-blue-500/20">
              {typeLabel}
            </span>
            <h3 className="text-sm font-semibold text-gray-200 truncate">{title}</h3>
          </div>
          <div className="flex items-center gap-1 ml-2 shrink-0">
            <button
              onClick={handleDownload}
              className="rounded-md p-1.5 text-gray-400 hover:text-gray-200 hover:bg-gray-700 transition-colors"
              title="SVG 다운로드"
            >
              <Download size={16} />
            </button>
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="rounded-md p-1.5 text-gray-400 hover:text-gray-200 hover:bg-gray-700 transition-colors"
              title={isExpanded ? '축소' : '확대'}
            >
              {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
          </div>
        </div>

        {/* SVG Content */}
        <div
          ref={containerRef}
          className={`flex items-center justify-center bg-white p-4 ${isExpanded ? 'h-[calc(100%-48px)]' : 'max-h-[600px]'}`}
          dangerouslySetInnerHTML={{ __html: sanitizedSvg }}
        />

        {/* Description */}
        {description && (
          <div className="px-4 py-2 border-t border-gray-700 bg-gray-800/50">
            <p className="text-xs text-gray-400">{description}</p>
          </div>
        )}
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
