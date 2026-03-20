'use client';

import { useEffect, useRef, useState, useId } from 'react';
import mermaid from 'mermaid';
import { Download, Maximize2, Minimize2, Copy, Check } from 'lucide-react';

// Mermaid 초기화 (한 번만)
let mermaidInitialized = false;

function initMermaid() {
  if (mermaidInitialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: 'neutral',
    fontFamily: 'Malgun Gothic, sans-serif',
    fontSize: 14,
    flowchart: {
      htmlLabels: true,
      curve: 'basis',
      padding: 15,
      nodeSpacing: 50,
      rankSpacing: 50,
      useMaxWidth: true,
    },
    sequence: {
      useMaxWidth: true,
      actorMargin: 50,
      mirrorActors: false,
    },
    gantt: {
      useMaxWidth: true,
      fontSize: 12,
    },
    er: {
      useMaxWidth: true,
    },
    pie: {
      useMaxWidth: true,
    },
    themeVariables: {
      primaryColor: '#4A90D9',
      primaryTextColor: '#1E293B',
      primaryBorderColor: '#3B82F6',
      lineColor: '#94A3B8',
      secondaryColor: '#F1F5F9',
      tertiaryColor: '#F8FAFC',
      noteBkgColor: '#FEF3C7',
      noteTextColor: '#92400E',
    },
  });
  mermaidInitialized = true;
}

interface MermaidDiagramProps {
  code: string;
}

export function MermaidDiagram({ code }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const uniqueId = useId().replace(/:/g, '_');

  useEffect(() => {
    initMermaid();

    const renderDiagram = async () => {
      try {
        // 문법 검증
        const isValid = await mermaid.parse(code);
        if (!isValid) {
          setError('Mermaid 문법 오류');
          return;
        }

        const { svg } = await mermaid.render(`mermaid_${uniqueId}`, code);
        setSvgContent(svg);
        setError(null);
      } catch (e: any) {
        console.error('Mermaid render error:', e);
        setError(e.message || 'Mermaid 렌더링 실패');
      }
    };

    renderDiagram();
  }, [code, uniqueId]);

  const handleDownload = () => {
    if (!svgContent) return;
    const blob = new Blob([svgContent], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'diagram.svg';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  };

  // 에러 시 코드 블록 폴백
  if (error) {
    return (
      <div className="my-4 rounded-lg border border-yellow-700/50 bg-yellow-900/20 p-4">
        <div className="mb-2 text-xs text-yellow-400">Mermaid 렌더링 실패: {error}</div>
        <pre className="overflow-auto rounded bg-gray-900 p-3 text-sm text-gray-300">
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  if (!svgContent) {
    return (
      <div className="my-4 flex h-32 items-center justify-center rounded-lg border border-gray-700 bg-gray-800">
        <div className="text-sm text-gray-400">다이어그램 렌더링 중...</div>
      </div>
    );
  }

  return (
    <div className="my-4">
      <div className={`rounded-lg border border-gray-700 bg-gray-800 overflow-hidden transition-all duration-200 ${isExpanded ? 'fixed inset-4 z-50' : ''}`}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-700 bg-gray-800/80">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center rounded-md bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400 ring-1 ring-inset ring-emerald-500/20">
              Mermaid
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={handleCopyCode}
              className="rounded-md p-1.5 text-gray-400 hover:text-gray-200 hover:bg-gray-700 transition-colors"
              title="코드 복사"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
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

        {/* Diagram */}
        <div
          ref={containerRef}
          className={`flex items-center justify-center bg-white p-6 overflow-auto ${isExpanded ? 'h-[calc(100%-44px)]' : 'max-h-[500px]'}`}
          dangerouslySetInnerHTML={{ __html: svgContent }}
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
