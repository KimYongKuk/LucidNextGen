"use client";

import { type ComponentProps, type HTMLAttributes, memo, useState, useEffect, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import { Streamdown } from "streamdown";
import { cn } from "@/lib/utils";
import { CodeBlock, CodeBlockCopyButton } from "@/components/elements/code-block";
import { FileDown, TableIcon, CheckIcon, Eye } from "lucide-react";
import { copyToClipboard } from "@/lib/clipboard";
import { useXlsxViewer } from "@/hooks/use-xlsx-viewer";
import { useDocumentViewer } from "@/hooks/use-document-viewer";

// PDF 다운로드 + 미리보기 링크 컴포넌트
const PDFDownloadLink = ({ filename }: { filename: string }) => {
  const { openFile } = useDocumentViewer();
  const downloadUrl = `/api/v1/pdf/download/${encodeURIComponent(filename)}`;

  return (
    <div className="inline-flex items-center gap-3">
      <button
        onClick={() => openFile(filename, "pdf")}
        className="inline-flex items-center gap-1.5 text-blue-600 dark:text-blue-400 hover:underline text-sm cursor-pointer"
      >
        <Eye className="w-4 h-4" />
        {filename} 미리보기
      </button>
      <a
        href={downloadUrl}
        download={filename}
        className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground text-sm"
      >
        <FileDown className="w-4 h-4" />
        다운로드
      </a>
    </div>
  );
};

// PPT 다운로드 링크 컴포넌트
const PPTDownloadLink = ({ filename }: { filename: string }) => {
  const downloadUrl = `/api/v1/ppt/download/${encodeURIComponent(filename)}`;

  return (
    <a
      href={downloadUrl}
      download={filename}
      className="inline-flex items-center gap-1.5 text-orange-600 dark:text-orange-400 hover:underline text-sm"
    >
      <FileDown className="w-4 h-4" />
      {filename} 다운로드
    </a>
  );
};

// DOCX 다운로드 + 미리보기 링크 컴포넌트
const DocxDownloadLink = ({ filename }: { filename: string }) => {
  const { openFile } = useDocumentViewer();
  const downloadUrl = `/api/v1/docx/download/${encodeURIComponent(filename)}`;

  return (
    <div className="inline-flex items-center gap-3">
      <button
        onClick={() => openFile(filename, "docx")}
        className="inline-flex items-center gap-1.5 text-indigo-600 dark:text-indigo-400 hover:underline text-sm cursor-pointer"
      >
        <Eye className="w-4 h-4" />
        {filename} 미리보기
      </button>
      <a
        href={downloadUrl}
        download={filename}
        className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground text-sm"
      >
        <FileDown className="w-4 h-4" />
        다운로드
      </a>
    </div>
  );
};

// XLSX 다운로드 + 미리보기 링크 컴포넌트
const XLSXDownloadLink = ({ filename }: { filename: string }) => {
  const { openFile } = useXlsxViewer();
  const downloadUrl = `/api/v1/xlsx/download/${encodeURIComponent(filename)}`;

  return (
    <div className="inline-flex items-center gap-3">
      <button
        onClick={() => openFile(filename)}
        className="inline-flex items-center gap-1.5 text-green-600 dark:text-green-400 hover:underline text-sm cursor-pointer"
      >
        <Eye className="w-4 h-4" />
        {filename} 미리보기
      </button>
      <a
        href={downloadUrl}
        download={filename}
        className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground text-sm"
      >
        <FileDown className="w-4 h-4" />
        다운로드
      </a>
    </div>
  );
};

// PDF 경로에서 파일명 추출 및 다운로드 링크로 변환
// workerName: 해당 워커일 때만 광범위 패턴(1,2) 활성화, 미지정 시 전체 활성(하위호환)
const processPDFContent = (content: string, workerName?: string): { processedContent: string; pdfFiles: string[] } => {
  const pdfFiles: string[] = [];
  // 워커 마커가 있으면 해당 워커만, 없으면 모든 패턴 활성 (기존 메시지 하위호환)
  // Note: 백엔드 INTENT_TO_WORKER는 PascalCase ("VisualizationWorker") 전송
  const useBroadPatterns = !workerName || /^visualization/i.test(workerName);

  // 파일명에서 백틱, 따옴표, 별표 등 특수문자 제거
  const cleanFilename = (filename: string): string => {
    let cleaned = filename
      .trim()
      .replace(/^[`'"*_\s]+|[`'"*_\s]+$/g, '')  // 앞뒤 백틱, 따옴표, 별표, 언더스코어, 공백 제거
      .replace(/[`'"]/g, '')                     // 중간의 백틱, 따옴표 제거
      .replace(/\*{2,}/g, '')                    // 연속된 별표(**) 제거 (마크다운 볼드)
      .replace(/_{2,}/g, '_')                    // 연속된 언더스코어를 하나로
      .replace(/^_+|_+$/g, '')                   // 앞뒤 남은 언더스코어 제거
      .replace(/\s+\.pdf$/i, '.pdf')             // .pdf 앞의 공백 제거
      .trim();

    // 경로가 포함된 경우 파일명만 추출
    const parts = cleaned.split(/[\\\/]/);
    return parts[parts.length - 1] || cleaned;
  };

  // 광범위 패턴 (해당 워커 또는 마커 없을 때만 활성)
  // 패턴 1: "파일명: xxx.pdf" 또는 "**파일명:** xxx.pdf" (백틱 포함 가능)
  // (?<![가-힣]) — "첨부파일명:" 등 복합어 내 false positive 방지
  const filenamePattern = /(?<![가-힣])\*?\*?파일명\*?\*?:\s*`?([^\n`]+\.pdf)`?/gi;
  // 패턴 2: "📄 파일: filename.pdf" 또는 "파일: filename.pdf" (백틱 포함 가능)
  // (?<![가-힣]) — "첨부파일:" 등 복합어 내 false positive 방지
  const filePattern = /(?:📄\s*)?(?<![가-힣])\*?\*?파일\*?\*?:\s*`?([^\n`]+\.pdf)`?/gi;
  // 경로 기반 패턴 (항상 활성 — 충분히 구체적)
  // 패턴 3: "pdf_output/filename.pdf" 또는 "pdf_output\\filename.pdf"
  const pathPattern = /pdf_output[/\\]([^\s\n`'"]+\.pdf)/gi;
  // 패턴 4: 전체 경로에서 파일명 추출 "C:\...\pdf_output\xxx.pdf"
  const fullPathPattern = /[A-Z]:[\\\/].*?[\\\/]pdf_output[\\\/]([^\s\n`'"]+\.pdf)/gi;

  let match;
  // 패턴 1, 2: 해당 워커일 때만 활성 (다른 워커의 false positive 방지)
  if (useBroadPatterns) {
    while ((match = filenamePattern.exec(content)) !== null) {
      const filename = cleanFilename(match[1]);
      if (filename && !pdfFiles.includes(filename)) {
        pdfFiles.push(filename);
      }
    }
    while ((match = filePattern.exec(content)) !== null) {
      const rawFilename = cleanFilename(match[1]);
      const justFilename = rawFilename.split(/[\\\/]/).pop() || rawFilename;
      if (justFilename && !pdfFiles.includes(justFilename)) {
        pdfFiles.push(justFilename);
      }
    }
  }
  // 패턴 3: pdf_output/ 상대 경로 (항상 활성)
  while ((match = pathPattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !pdfFiles.includes(filename)) {
      pdfFiles.push(filename);
    }
  }
  // 패턴 4: 전체 경로 (항상 활성)
  while ((match = fullPathPattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !pdfFiles.includes(filename)) {
      pdfFiles.push(filename);
    }
  }

  // 경로 정보 라인 제거 (다운로드 버튼으로 대체) - bold 마크다운 포함
  let processedContent = content
    .replace(/\*?\*?파일명\*?\*?:\s*[^\n]+\.pdf\*?\*?\n?/gi, '')
    .replace(/\*?\*?파일 위치\*?\*?:\s*[^\n]+\n?/gi, '')
    .replace(/\*?\*?저장 위치\*?\*?:\s*[^\n]+\n?/gi, '')
    .replace(/📁\s*경로:\s*[^\n]+\.pdf\n?/gi, '')
    .replace(/📄\s*파일:\s*[^\n]+\.pdf\n?/gi, '');

  return { processedContent, pdfFiles };
};

// PPT 경로에서 파일명 추출 및 다운로드 링크로 변환
const processPPTContent = (content: string, workerName?: string): { processedContent: string; pptFiles: string[] } => {
  const pptFiles: string[] = [];
  // Note: 백엔드 INTENT_TO_WORKER는 PascalCase ("PPTWorker") 전송
  const useBroadPatterns = !workerName || /^ppt/i.test(workerName);

  const cleanFilename = (filename: string): string => {
    let cleaned = filename
      .trim()
      .replace(/^[`'"*_\s]+|[`'"*_\s]+$/g, '')
      .replace(/[`'"]/g, '')
      .replace(/\*{2,}/g, '')
      .replace(/_{2,}/g, '_')
      .replace(/^_+|_+$/g, '')
      .replace(/\s+\.pptx$/i, '.pptx')
      .trim();
    const parts = cleaned.split(/[\\\/]/);
    return parts[parts.length - 1] || cleaned;
  };

  // 광범위 패턴 (해당 워커 또는 마커 없을 때만 활성)
  // (?<![가-힣]) — "첨부파일:" 등 복합어 내 false positive 방지
  const filenamePattern = /(?<![가-힣])\*?\*?파일명\*?\*?:\s*`?([^\n`]+\.pptx)`?/gi;
  const filePattern = /(?:📊\s*)?(?<![가-힣])\*?\*?파일\*?\*?:\s*`?([^\n`]+\.pptx)`?/gi;
  // 경로 기반 패턴 (항상 활성)
  const pathPattern = /ppt_output[/\\]([^\s\n`'"]+\.pptx)/gi;
  const fullPathPattern = /[A-Z]:[\\\/].*?[\\\/]ppt_output[\\\/]([^\s\n`'"]+\.pptx)/gi;

  let match;
  if (useBroadPatterns) {
    while ((match = filenamePattern.exec(content)) !== null) {
      const filename = cleanFilename(match[1]);
      if (filename && !pptFiles.includes(filename)) pptFiles.push(filename);
    }
    while ((match = filePattern.exec(content)) !== null) {
      const rawFilename = cleanFilename(match[1]);
      const justFilename = rawFilename.split(/[\\\/]/).pop() || rawFilename;
      if (justFilename && !pptFiles.includes(justFilename)) pptFiles.push(justFilename);
    }
  }
  while ((match = pathPattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !pptFiles.includes(filename)) pptFiles.push(filename);
  }
  while ((match = fullPathPattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !pptFiles.includes(filename)) pptFiles.push(filename);
  }

  let processedContent = content
    .replace(/\*?\*?파일명\*?\*?:\s*[^\n]+\.pptx\*?\*?\n?/gi, '')
    .replace(/\*?\*?파일 위치\*?\*?:\s*[^\n]*ppt_output[^\n]*\n?/gi, '')
    .replace(/\*?\*?저장 위치\*?\*?:\s*[^\n]*ppt_output[^\n]*\n?/gi, '')
    .replace(/\*?\*?경로\*?\*?:\s*[^\n]*ppt_output[^\n]*\n?/gi, '');

  return { processedContent, pptFiles };
};

// XLSX 경로에서 파일명 추출 및 다운로드 링크로 변환
const processXLSXContent = (content: string, workerName?: string): { processedContent: string; xlsxFiles: string[] } => {
  const xlsxFiles: string[] = [];
  // Note: 백엔드 INTENT_TO_WORKER는 PascalCase ("XlsxWorker") 전송
  const useBroadPatterns = !workerName || /^xlsx/i.test(workerName);

  const cleanFilename = (filename: string): string => {
    let cleaned = filename
      .trim()
      .replace(/^[`'"*_\s]+|[`'"*_\s]+$/g, '')
      .replace(/[`'"]/g, '')
      .replace(/\*{2,}/g, '')
      .replace(/_{2,}/g, '_')
      .replace(/^_+|_+$/g, '')
      .replace(/\s+\.xlsx$/i, '.xlsx')
      .trim();
    const parts = cleaned.split(/[\\\/]/);
    return parts[parts.length - 1] || cleaned;
  };

  // 광범위 패턴 (해당 워커 또는 마커 없을 때만 활성)
  // (?<![가-힣]) — "첨부파일:" 등 복합어 내 false positive 방지
  const filenamePattern = /(?<![가-힣])\*?\*?파일명\*?\*?:\s*`?([^\n`]+\.xlsx)`?/gi;
  const filePattern = /(?:📊\s*)?(?<![가-힣])\*?\*?파일\*?\*?:\s*`?([^\n`]+\.xlsx)`?/gi;
  // 경로 기반 패턴 (항상 활성)
  const pathPattern = /xlsx_output[/\\]([^\s\n`'"]+\.xlsx)/gi;
  const fullPathPattern = /[A-Z]:[\\\/].*?[\\\/]xlsx_output[\\\/]([^\s\n`'"]+\.xlsx)/gi;

  let match;
  if (useBroadPatterns) {
    while ((match = filenamePattern.exec(content)) !== null) {
      const filename = cleanFilename(match[1]);
      if (filename && !xlsxFiles.includes(filename)) xlsxFiles.push(filename);
    }
    while ((match = filePattern.exec(content)) !== null) {
      const rawFilename = cleanFilename(match[1]);
      const justFilename = rawFilename.split(/[\\\/]/).pop() || rawFilename;
      if (justFilename && !xlsxFiles.includes(justFilename)) xlsxFiles.push(justFilename);
    }
  }
  while ((match = pathPattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !xlsxFiles.includes(filename)) xlsxFiles.push(filename);
  }
  while ((match = fullPathPattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !xlsxFiles.includes(filename)) xlsxFiles.push(filename);
  }

  let processedContent = content
    .replace(/\*?\*?파일명\*?\*?:\s*[^\n]+\.xlsx\*?\*?\n?/gi, '')
    .replace(/\*?\*?파일 위치\*?\*?:\s*[^\n]*xlsx_output[^\n]*\n?/gi, '')
    .replace(/\*?\*?저장 위치\*?\*?:\s*[^\n]*xlsx_output[^\n]*\n?/gi, '')
    .replace(/\*?\*?경로\*?\*?:\s*[^\n]*xlsx_output[^\n]*\n?/gi, '');

  return { processedContent, xlsxFiles };
};

// DOCX 경로에서 파일명 추출 및 다운로드 링크로 변환
const processDocxContent = (content: string, workerName?: string): { processedContent: string; docxFiles: string[] } => {
  const docxFiles: string[] = [];
  const useBroadPatterns = !workerName || /^visualization/i.test(workerName);

  const cleanFilename = (filename: string): string => {
    let cleaned = filename
      .trim()
      .replace(/^[`'"*_\s]+|[`'"*_\s]+$/g, '')
      .replace(/[`'"]/g, '')
      .replace(/\*{2,}/g, '')
      .replace(/_{2,}/g, '_')
      .replace(/^_+|_+$/g, '')
      .replace(/\s+\.docx$/i, '.docx')
      .trim();
    const parts = cleaned.split(/[\\\/]/);
    return parts[parts.length - 1] || cleaned;
  };

  const filenamePattern = /(?<![가-힣])\*?\*?파일명\*?\*?:\s*`?([^\n`]+\.docx)`?/gi;
  const filePattern = /(?:📄\s*)?(?<![가-힣])\*?\*?파일\*?\*?:\s*`?([^\n`]+\.docx)`?/gi;
  const pathPattern = /docx_output[/\\]([^\s\n`'"]+\.docx)/gi;
  const fullPathPattern = /[A-Z]:[\\\/].*?[\\\/]docx_output[\\\/]([^\s\n`'"]+\.docx)/gi;

  let match;
  if (useBroadPatterns) {
    while ((match = filenamePattern.exec(content)) !== null) {
      const filename = cleanFilename(match[1]);
      if (filename && !docxFiles.includes(filename)) docxFiles.push(filename);
    }
    while ((match = filePattern.exec(content)) !== null) {
      const rawFilename = cleanFilename(match[1]);
      const justFilename = rawFilename.split(/[\\\/]/).pop() || rawFilename;
      if (justFilename && !docxFiles.includes(justFilename)) docxFiles.push(justFilename);
    }
  }
  while ((match = pathPattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !docxFiles.includes(filename)) docxFiles.push(filename);
  }
  while ((match = fullPathPattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !docxFiles.includes(filename)) docxFiles.push(filename);
  }

  let processedContent = content
    .replace(/\*?\*?파일명\*?\*?:\s*[^\n]+\.docx\*?\*?\n?/gi, '')
    .replace(/\*?\*?파일 위치\*?\*?:\s*[^\n]*docx_output[^\n]*\n?/gi, '')
    .replace(/\*?\*?저장 위치\*?\*?:\s*[^\n]*docx_output[^\n]*\n?/gi, '')
    .replace(/\*?\*?경로\*?\*?:\s*[^\n]*docx_output[^\n]*\n?/gi, '');

  return { processedContent, docxFiles };
};

// 테이블 래퍼 컴포넌트 - 엑셀 복사 버튼 포함
const TableWithCopyButton = ({ children, ...props }: HTMLAttributes<HTMLTableElement>) => {
  const tableRef = useRef<HTMLTableElement>(null);
  const [isCopied, setIsCopied] = useState(false);

  const handleCopyAsExcel = useCallback(async () => {
    const table = tableRef.current;
    if (!table) return;

    const rows = table.querySelectorAll("tr");
    const tsvLines: string[] = [];

    rows.forEach((row) => {
      const cells = row.querySelectorAll("th, td");
      const values: string[] = [];
      cells.forEach((cell) => {
        values.push((cell as HTMLElement).innerText.trim());
      });
      tsvLines.push(values.join("\t"));
    });

    const tsv = tsvLines.join("\n");
    const success = await copyToClipboard(tsv);
    if (success) {
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    }
  }, []);

  return (
    <div className="relative group/table my-4">
      <button
        onClick={handleCopyAsExcel}
        className="absolute -top-3 right-1 z-10 opacity-0 group-hover/table:opacity-100 transition-opacity inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-muted hover:bg-accent border border-border shadow-sm cursor-pointer"
        title="엑셀에 붙여넣기용 복사 (탭 구분)"
      >
        {isCopied ? (
          <>
            <CheckIcon className="w-3 h-3 text-green-600" />
            <span className="text-green-600">Copied!</span>
          </>
        ) : (
          <>
            <TableIcon className="w-3 h-3" />
            <span>Copy for Excel</span>
          </>
        )}
      </button>
      <table ref={tableRef} {...props}>
        {children}
      </table>
    </div>
  );
};

// 타이핑 효과 컴포넌트 (무한 반복)
const TypewriterText = ({
  text,
  speed = 50,
  pauseDuration = 1000,
  className
}: {
  text: string;
  speed?: number;
  pauseDuration?: number;
  className?: string;
}) => {
  const [displayedText, setDisplayedText] = useState("");
  const prevTextRef = useRef(text);

  useEffect(() => {
    // 텍스트가 변경되면 리셋
    if (prevTextRef.current !== text) {
      setDisplayedText("");
      prevTextRef.current = text;
    }

    if (displayedText.length < text.length) {
      // 타이핑 중
      const timer = setTimeout(() => {
        setDisplayedText(text.slice(0, displayedText.length + 1));
      }, speed);
      return () => clearTimeout(timer);
    } else {
      // 타이핑 완료 후 잠시 대기 후 다시 시작
      const timer = setTimeout(() => {
        setDisplayedText("");
      }, pauseDuration);
      return () => clearTimeout(timer);
    }
  }, [text, displayedText, speed, pauseDuration]);

  return (
    <span className={className}>
      {displayedText}
      <span className="animate-pulse ml-0.5 inline-block w-0.5 h-4 bg-current align-middle" />
    </span>
  );
};

type ResponseProps = ComponentProps<typeof Streamdown> & {
  isStreaming?: boolean;
  workerName?: string;
};

export const Response = memo(
  ({ className, isStreaming = false, workerName: workerNameProp, ...props }: ResponseProps) => {
    const rawContent = props.children as string;

    // workerName: prop으로 전달받은 값 사용, 하위호환을 위해 텍스트 마커도 fallback 처리
    const legacyMatch = (rawContent || "").match(/^<!--WORKER:(\w+)-->/);
    const workerName = workerNameProp || legacyMatch?.[1];
    const content = legacyMatch ? (rawContent || "").slice(legacyMatch[0].length) : (rawContent || "");

    // Tool 상태, 대기 상태, Fallback 마커 감지 및 처리
    const toolStatusRegex = /__TOOL_STATUS__:(.*?)__END__/g;
    const waitingRegex = /__WAITING__:(.*?)__END__/g;
    const fallbackRegex = /__FALLBACK__:(.*?)__END__/g;

    const processedContent = content?.replace(toolStatusRegex, (_, message) => {
      // 마커를 애니메이션이 적용된 HTML로 변환 (마크다운은 그대로 통과)
      return `\n\n**${message}**\n\n`;
    });

    // Tool 상태, 대기 상태, 또는 Fallback 메시지가 있는지 확인
    const hasToolStatus = /__TOOL_STATUS__:(.*?)__END__/.test(content || '');
    const hasWaiting = /__WAITING__:(.*?)__END__/.test(content || '');
    const hasFallback = /__FALLBACK__:(.*?)__END__/.test(content || '');

    if (hasToolStatus || hasWaiting || hasFallback) {
      // 애니메이션이 필요한 경우
      return (
        <div
          className={cn(
            "size-full whitespace-pre-wrap break-words",
            className
          )}
        >
          {content?.split(/(__TOOL_STATUS__:.*?__END__|__WAITING__:.*?__END__|__FALLBACK__:.*?__END__)/).map((part, idx) => {
            // Tool 상태 메시지 감지 (타이핑 효과)
            if (part?.startsWith('__TOOL_STATUS__:')) {
              const message = part.replace(/__TOOL_STATUS__:(.*?)__END__/, '$1');
              return (
                <div key={idx} className="my-2 inline-flex items-center gap-2">
                  <TypewriterText
                    text={message}
                    speed={40}
                    className="text-muted-foreground font-medium"
                  />
                </div>
              );
            }
            // 대기 상태 메시지 감지 (노란색 타이핑 효과)
            if (part?.startsWith('__WAITING__:')) {
              const message = part.replace(/__WAITING__:(.*?)__END__/, '$1');
              return (
                <div key={idx} className="my-2 inline-flex items-center gap-2">
                  <TypewriterText
                    text={message}
                    speed={35}
                    className="text-yellow-600 dark:text-yellow-500 font-medium"
                  />
                </div>
              );
            }
            // Fallback 메시지 감지 (주황색 타이핑 효과)
            if (part?.startsWith('__FALLBACK__:')) {
              const message = part.replace(/__FALLBACK__:(.*?)__END__/, '$1');
              return (
                <div key={idx} className="my-2 inline-flex items-center gap-2">
                  <TypewriterText
                    text={message}
                    speed={35}
                    className="text-orange-600 dark:text-orange-500 font-medium"
                  />
                </div>
              );
            }
            // 빈 문자열이나 매칭된 전체 문자열은 스킵
            if (!part || part.includes('__TOOL_STATUS__') || part.includes('__WAITING__') || part.includes('__FALLBACK__')) {
              return null;
            }
            // 일반 텍스트
            return <span key={idx}>{part}</span>;
          })}
        </div>
      );
    }

    // PDF 파일 감지 및 처리 (workerName으로 false positive 방지)
    const { processedContent: pdfProcessed, pdfFiles } = processPDFContent(content, workerName);
    // PPT 파일 감지 및 처리
    const { processedContent: pptProcessed, pptFiles } = processPPTContent(pdfProcessed, workerName);
    // XLSX 파일 감지 및 처리
    const { processedContent: xlsxProcessed, xlsxFiles } = processXLSXContent(pptProcessed, workerName);
    // DOCX 파일 감지 및 처리
    const { processedContent: markdownContent, docxFiles } = processDocxContent(xlsxProcessed, workerName);

    // 마크다운 렌더링
    return (
      <div className={cn("size-full prose prose-sm max-w-none dark:prose-invert", className)}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkBreaks]}
          components={{
            p({ children, ...props }: any) {
              // Hydration 에러 방지: <p> 안에 <pre>, <div> 등 블록 요소가 들어가지 않도록
              const childArray = Array.isArray(children) ? children : [children];
              const hasBlockElement = childArray.some((child: any) => {
                if (typeof child === "object" && child !== null && child.type) {
                  const type = child.type;
                  if (typeof type === "string") {
                    return ["pre", "div", "table", "ul", "ol", "blockquote", "hr"].includes(type);
                  }
                  // React 컴포넌트 (CodeBlock 등) - 블록 요소를 렌더링할 수 있음
                  return typeof type === "function" || typeof type === "object";
                }
                return false;
              });
              if (hasBlockElement) {
                return <div {...props}>{children}</div>;
              }
              return <p {...props}>{children}</p>;
            },
            table({ children, ...props }: any) {
              return <TableWithCopyButton {...props}>{children}</TableWithCopyButton>;
            },
            code({ node, className, children, ...props }: any) {
              const match = /language-(\w+)/.exec(className || "");
              const codeString = String(children).replace(/\n$/, "");

              // react-markdown v9+: inline prop이 제거됨
              // 블록 코드 판별: language class가 있거나 개행 포함
              const isInline = !className && !codeString.includes('\n');

              // 블록 코드 (언어 지정 또는 미지정)
              if (!isInline) {
                if (isStreaming) {
                  return (
                    <pre className="my-4 overflow-auto rounded-md border bg-background p-4">
                      <code className="font-mono text-sm">{codeString}</code>
                    </pre>
                  );
                }
                return (
                  <CodeBlock
                    code={codeString}
                    language={match ? match[1] : "text"}
                    className="my-4"
                  >
                    <CodeBlockCopyButton />
                  </CodeBlock>
                );
              }

              // 인라인 코드
              return (
                <code className={cn("bg-muted px-1.5 py-0.5 rounded text-sm", className)} {...props}>
                  {children}
                </code>
              );
            },
          }}
        >
          {markdownContent}
        </ReactMarkdown>

        {/* PDF 다운로드 링크 */}
        {pdfFiles.length > 0 && (
          <div className="mt-3 flex flex-col gap-1">
            {pdfFiles.map((filename, idx) => (
              <PDFDownloadLink key={idx} filename={filename} />
            ))}
          </div>
        )}

        {/* PPT 다운로드 링크 */}
        {pptFiles.length > 0 && (
          <div className="mt-3 flex flex-col gap-1">
            {pptFiles.map((filename, idx) => (
              <PPTDownloadLink key={idx} filename={filename} />
            ))}
          </div>
        )}

        {/* XLSX 다운로드 링크 */}
        {xlsxFiles.length > 0 && (
          <div className="mt-3 flex flex-col gap-1">
            {xlsxFiles.map((filename, idx) => (
              <XLSXDownloadLink key={idx} filename={filename} />
            ))}
          </div>
        )}

        {/* DOCX 다운로드 링크 */}
        {docxFiles.length > 0 && (
          <div className="mt-3 flex flex-col gap-1">
            {docxFiles.map((filename, idx) => (
              <DocxDownloadLink key={idx} filename={filename} />
            ))}
          </div>
        )}
      </div>
    );
  },
  (prevProps, nextProps) =>
    prevProps.children === nextProps.children &&
    prevProps.isStreaming === nextProps.isStreaming &&
    prevProps.workerName === nextProps.workerName
);

Response.displayName = "Response";
