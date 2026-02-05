"use client";

import { CheckIcon, CopyIcon } from "lucide-react";
import type { ComponentProps, HTMLAttributes, ReactNode } from "react";
import { createContext, useContext, useState, useMemo, memo } from "react";
import { useTheme } from "next-themes";
// PrismLight 버전 사용으로 번들 크기 대폭 감소 (전체 Prism 대신 필요한 언어만 로드)
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import {
  oneDark,
  oneLight,
} from "react-syntax-highlighter/dist/cjs/styles/prism";

// 자주 사용하는 언어만 등록 (필요시 추가)
import javascript from "react-syntax-highlighter/dist/cjs/languages/prism/javascript";
import typescript from "react-syntax-highlighter/dist/cjs/languages/prism/typescript";
import python from "react-syntax-highlighter/dist/cjs/languages/prism/python";
import json from "react-syntax-highlighter/dist/cjs/languages/prism/json";
import bash from "react-syntax-highlighter/dist/cjs/languages/prism/bash";
import sql from "react-syntax-highlighter/dist/cjs/languages/prism/sql";
import css from "react-syntax-highlighter/dist/cjs/languages/prism/css";
import jsx from "react-syntax-highlighter/dist/cjs/languages/prism/jsx";
import tsx from "react-syntax-highlighter/dist/cjs/languages/prism/tsx";
import markdown from "react-syntax-highlighter/dist/cjs/languages/prism/markdown";

// 언어 등록
SyntaxHighlighter.registerLanguage("javascript", javascript);
SyntaxHighlighter.registerLanguage("js", javascript);
SyntaxHighlighter.registerLanguage("typescript", typescript);
SyntaxHighlighter.registerLanguage("ts", typescript);
SyntaxHighlighter.registerLanguage("python", python);
SyntaxHighlighter.registerLanguage("py", python);
SyntaxHighlighter.registerLanguage("json", json);
SyntaxHighlighter.registerLanguage("bash", bash);
SyntaxHighlighter.registerLanguage("sh", bash);
SyntaxHighlighter.registerLanguage("shell", bash);
SyntaxHighlighter.registerLanguage("sql", sql);
SyntaxHighlighter.registerLanguage("css", css);
SyntaxHighlighter.registerLanguage("jsx", jsx);
SyntaxHighlighter.registerLanguage("tsx", tsx);
SyntaxHighlighter.registerLanguage("markdown", markdown);
SyntaxHighlighter.registerLanguage("md", markdown);
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { copyToClipboard as copyToClipboardFallback } from "@/lib/clipboard"; // HTTPS + HTTP fallback 지원

type CodeBlockContextType = {
  code: string;
};

const CodeBlockContext = createContext<CodeBlockContextType>({
  code: "",
});

export type CodeBlockProps = HTMLAttributes<HTMLDivElement> & {
  code: string;
  language: string;
  showLineNumbers?: boolean;
  children?: ReactNode;
};

// 스타일 객체를 컴포넌트 외부에 정의하여 재생성 방지
const codeTagProps = { className: "font-mono text-sm" };
const customStyle = {
  margin: 0,
  padding: "1rem",
  fontSize: "0.875rem",
  background: "hsl(var(--background))",
  color: "hsl(var(--foreground))",
  overflowX: "auto" as const,
  overflowWrap: "break-word" as const,
  wordBreak: "break-all" as const,
};
const lineNumberStyle = {
  color: "hsl(var(--muted-foreground))",
  paddingRight: "1rem",
  minWidth: "2.5rem",
};

export const CodeBlock = memo(({
  code,
  language,
  showLineNumbers = false,
  className,
  children,
  ...props
}: CodeBlockProps) => {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  // 테마 스타일만 memoize (테마 변경 시에만 재계산)
  const themeStyle = useMemo(() => isDark ? oneDark : oneLight, [isDark]);

  // context value memoize
  const contextValue = useMemo(() => ({ code }), [code]);

  return (
    <CodeBlockContext.Provider value={contextValue}>
      <div
        className={cn(
          "relative w-full overflow-hidden rounded-md border bg-background text-foreground",
          className
        )}
        {...props}
      >
        <div className="relative">
          <SyntaxHighlighter
            className="overflow-hidden"
            codeTagProps={codeTagProps}
            customStyle={customStyle}
            language={language}
            lineNumberStyle={lineNumberStyle}
            showLineNumbers={showLineNumbers}
            style={themeStyle}
          >
            {code}
          </SyntaxHighlighter>
          {children && (
            <div className="absolute top-2 right-2 flex items-center gap-2">
              {children}
            </div>
          )}
        </div>
      </div>
    </CodeBlockContext.Provider>
  );
});

export type CodeBlockCopyButtonProps = ComponentProps<typeof Button> & {
  onCopy?: () => void;
  onError?: (error: Error) => void;
  timeout?: number;
};

export const CodeBlockCopyButton = ({
  onCopy,
  onError,
  timeout = 2000,
  children,
  className,
  ...props
}: CodeBlockCopyButtonProps) => {
  const [isCopied, setIsCopied] = useState(false);
  const { code } = useContext(CodeBlockContext);

  /**
   * 코드 블록 복사 핸들러
   *
   * @description
   * - HTTPS/localhost: navigator.clipboard API 사용
   * - HTTP (외부 접근): execCommand fallback 자동 적용
   * - 복사 성공 시 체크 아이콘으로 2초간 표시
   * - 복사 실패 시 onError 콜백 호출
   */
  const handleCopyClick = async () => {
    // SSR 환경 체크
    if (typeof window === "undefined") {
      onError?.(new Error("Window is not available (SSR environment)"));
      return;
    }

    // 복사할 코드가 없는 경우
    if (!code || code.trim().length === 0) {
      onError?.(new Error("No code to copy"));
      return;
    }

    try {
      // fallback이 포함된 복사 함수 호출
      const success = await copyToClipboardFallback(code);

      if (success) {
        // 복사 성공: 체크 아이콘 표시 및 콜백 실행
        setIsCopied(true);
        onCopy?.();

        // timeout 후 원래 상태로 복구
        setTimeout(() => setIsCopied(false), timeout);
      } else {
        // 복사 실패
        throw new Error("Failed to copy code to clipboard");
      }
    } catch (error) {
      // 에러 핸들링
      console.error("Code copy error:", error);
      onError?.(error as Error);
    }
  };

  // 복사 상태에 따라 아이콘 변경
  const Icon = isCopied ? CheckIcon : CopyIcon;

  return (
    <Button
      className={cn("shrink-0", className)}
      onClick={handleCopyClick}
      size="icon"
      variant="ghost"
      {...props}
    >
      {children ?? <Icon size={14} />}
    </Button>
  );
};
