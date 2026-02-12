"use client";

import { type ComponentProps, memo, useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import { Streamdown } from "streamdown";
import { cn } from "@/lib/utils";
import { CodeBlock, CodeBlockCopyButton } from "@/components/elements/code-block";
import { FileDown } from "lucide-react";

// PDF 다운로드 링크 컴포넌트
const PDFDownloadLink = ({ filename }: { filename: string }) => {
  // 상대 경로 사용 - Next.js rewrites로 백엔드로 프록시
  const downloadUrl = `/api/v1/pdf/download/${encodeURIComponent(filename)}`;

  return (
    <a
      href={downloadUrl}
      download={filename}
      className="inline-flex items-center gap-1.5 text-blue-600 dark:text-blue-400 hover:underline text-sm"
    >
      <FileDown className="w-4 h-4" />
      {filename} 다운로드
    </a>
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

// PDF 경로에서 파일명 추출 및 다운로드 링크로 변환
const processPDFContent = (content: string): { processedContent: string; pdfFiles: string[] } => {
  const pdfFiles: string[] = [];

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

  // 패턴들 (bold 마크다운 **xxx:** 형식도 포함)
  // 패턴 1: "파일명: xxx.pdf" 또는 "**파일명:** xxx.pdf" (백틱 포함 가능)
  const filenamePattern = /\*?\*?파일명\*?\*?:\s*`?([^\n`]+\.pdf)`?/gi;
  // 패턴 2: "📄 파일: filename.pdf" 또는 "파일: filename.pdf" (백틱 포함 가능)
  const filePattern = /(?:📄\s*)?\*?\*?파일\*?\*?:\s*`?([^\n`]+\.pdf)`?/gi;
  // 패턴 3: "pdf_output/filename.pdf" 또는 "pdf_output\\filename.pdf"
  const pathPattern = /pdf_output[/\\]([^\s\n`'"]+\.pdf)/gi;
  // 패턴 4: 전체 경로에서 파일명 추출 "C:\...\pdf_output\xxx.pdf"
  const fullPathPattern = /[A-Z]:[\\\/].*?[\\\/]pdf_output[\\\/]([^\s\n`'"]+\.pdf)/gi;

  let match;
  // 패턴 1: 파일명:
  while ((match = filenamePattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !pdfFiles.includes(filename)) {
      pdfFiles.push(filename);
    }
  }
  // 패턴 2: 파일:
  while ((match = filePattern.exec(content)) !== null) {
    const rawFilename = cleanFilename(match[1]);
    // 전체 경로가 아닌 파일명만 추출
    const justFilename = rawFilename.split(/[\\\/]/).pop() || rawFilename;
    if (justFilename && !pdfFiles.includes(justFilename)) {
      pdfFiles.push(justFilename);
    }
  }
  // 패턴 3: pdf_output/ 상대 경로
  while ((match = pathPattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !pdfFiles.includes(filename)) {
      pdfFiles.push(filename);
    }
  }
  // 패턴 4: 전체 경로
  while ((match = fullPathPattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !pdfFiles.includes(filename)) {
      pdfFiles.push(filename);
    }
  }

  // 경로 정보 라인 제거 (다운로드 버튼으로 대체) - bold 마크다운 포함
  let processedContent = content
    .replace(/\*?\*?파일명\*?\*?:\s*[^\n]+\.pdf\n?/gi, '')
    .replace(/\*?\*?파일 위치\*?\*?:\s*[^\n]+\n?/gi, '')
    .replace(/\*?\*?저장 위치\*?\*?:\s*[^\n]+\n?/gi, '')
    .replace(/📁\s*경로:\s*[^\n]+\.pdf\n?/gi, '')
    .replace(/📄\s*파일:\s*[^\n]+\.pdf\n?/gi, '');

  return { processedContent, pdfFiles };
};

// PPT 경로에서 파일명 추출 및 다운로드 링크로 변환
const processPPTContent = (content: string): { processedContent: string; pptFiles: string[] } => {
  const pptFiles: string[] = [];

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

  // 패턴 1: "파일명: xxx.pptx"
  const filenamePattern = /\*?\*?파일명\*?\*?:\s*`?([^\n`]+\.pptx)`?/gi;
  // 패턴 2: "파일: xxx.pptx"
  const filePattern = /(?:📊\s*)?\*?\*?파일\*?\*?:\s*`?([^\n`]+\.pptx)`?/gi;
  // 패턴 3: "ppt_output/xxx.pptx"
  const pathPattern = /ppt_output[/\\]([^\s\n`'"]+\.pptx)/gi;
  // 패턴 4: 전체 경로
  const fullPathPattern = /[A-Z]:[\\\/].*?[\\\/]ppt_output[\\\/]([^\s\n`'"]+\.pptx)/gi;

  let match;
  while ((match = filenamePattern.exec(content)) !== null) {
    const filename = cleanFilename(match[1]);
    if (filename && !pptFiles.includes(filename)) pptFiles.push(filename);
  }
  while ((match = filePattern.exec(content)) !== null) {
    const rawFilename = cleanFilename(match[1]);
    const justFilename = rawFilename.split(/[\\\/]/).pop() || rawFilename;
    if (justFilename && !pptFiles.includes(justFilename)) pptFiles.push(justFilename);
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
    .replace(/\*?\*?파일명\*?\*?:\s*[^\n]+\.pptx\n?/gi, '')
    .replace(/\*?\*?파일 위치\*?\*?:\s*[^\n]*ppt_output[^\n]*\n?/gi, '')
    .replace(/\*?\*?저장 위치\*?\*?:\s*[^\n]*ppt_output[^\n]*\n?/gi, '')
    .replace(/\*?\*?경로\*?\*?:\s*[^\n]*ppt_output[^\n]*\n?/gi, '');

  return { processedContent, pptFiles };
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
};

export const Response = memo(
  ({ className, isStreaming = false, ...props }: ResponseProps) => {
    // Tool 상태, 대기 상태, Fallback 마커 감지 및 처리
    const content = props.children as string;
    const toolStatusRegex = /__TOOL_STATUS__:(.*?)__END__/g;
    const waitingRegex = /__WAITING__:(.*?)__END__/g;
    const fallbackRegex = /__FALLBACK__:(.*?)__END__/g;

    const processedContent = content?.replace(toolStatusRegex, (_, message) => {
      // 마커를 애니메이션이 적용된 HTML로 변환 (마크다운은 그대로 통과)
      return `\n\n**${message}**\n\n`;
    });

    // Tool 상태, 대기 상태, 또는 Fallback 메시지가 있는지 확인
    const hasToolStatus = toolStatusRegex.test(content || '');
    const hasWaiting = waitingRegex.test(content || '');
    const hasFallback = fallbackRegex.test(content || '');

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

    // PDF 파일 감지 및 처리
    const { processedContent: pdfProcessed, pdfFiles } = processPDFContent(content || "");
    // PPT 파일 감지 및 처리
    const { processedContent: markdownContent, pptFiles } = processPPTContent(pdfProcessed);

    // 마크다운 렌더링
    return (
      <div className={cn("size-full prose prose-sm max-w-none dark:prose-invert", className)}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkBreaks]}
          components={{
            code({ node, inline, className, children, ...props }: any) {
              const match = /language-(\w+)/.exec(className || "");
              const codeString = String(children).replace(/\n$/, "");

              // 스트리밍 중에는 하이라이팅 없이 단순 pre/code 렌더링 (성능 최적화)
              if (!inline && match) {
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
                    language={match[1]}
                    className="my-4"
                  >
                    <CodeBlockCopyButton />
                  </CodeBlock>
                );
              }

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
      </div>
    );
  },
  (prevProps, nextProps) =>
    prevProps.children === nextProps.children &&
    prevProps.isStreaming === nextProps.isStreaming
);

Response.displayName = "Response";
