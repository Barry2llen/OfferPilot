import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface MarkdownContentProps {
  content: string;
  inverse?: boolean;
  className?: string;
}

export default function MarkdownContent({
  content,
  inverse = false,
  className = "",
}: MarkdownContentProps) {
  if (!content) {
    return null;
  }

  const textClass = inverse ? "text-white" : "text-text-primary";
  const mutedClass = inverse ? "text-white/70" : "text-text-secondary";
  const borderClass = inverse ? "border-white/15" : "border-border-default";
  const codeClass = inverse
    ? "bg-white/10 text-white"
    : "bg-white text-text-charcoal";
  const linkClass = inverse
    ? "text-primary-200 hover:text-white"
    : "text-primary-600 hover:text-primary-700";

  const components: Components = {
    p({ children }) {
      return <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>;
    },
    a({ children, href }) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className={`${linkClass} underline underline-offset-2`}
        >
          {children}
        </a>
      );
    },
    ul({ children }) {
      return <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>;
    },
    ol({ children }) {
      return <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>;
    },
    li({ children }) {
      return <li className="pl-1">{children}</li>;
    },
    blockquote({ children }) {
      return (
        <blockquote className={`my-2 border-l-2 ${borderClass} pl-3 ${mutedClass}`}>
          {children}
        </blockquote>
      );
    },
    h1({ children }) {
      return <h1 className="mb-2 text-lg font-semibold leading-tight">{children}</h1>;
    },
    h2({ children }) {
      return <h2 className="mb-2 text-base font-semibold leading-tight">{children}</h2>;
    },
    h3({ children }) {
      return <h3 className="mb-1.5 text-sm font-semibold leading-tight">{children}</h3>;
    },
    hr() {
      return <hr className={`my-3 border-0 border-t ${borderClass}`} />;
    },
    pre({ children }) {
      return <CodeBlockWrapper codeClass={codeClass}>{children}</CodeBlockWrapper>;
    },
    code({ children, className }) {
      return (
        <code
          className={`rounded px-1 py-0.5 font-mono text-[0.9em] ${codeClass} ${className ?? ""}`}
        >
          {children}
        </code>
      );
    },
    table({ children }) {
      return (
        <div className="my-2 max-w-full overflow-x-auto">
          <table className={`w-full border-collapse text-xs ${textClass}`}>
            {children}
          </table>
        </div>
      );
    },
    th({ children }) {
      return (
        <th className={`border ${borderClass} px-2 py-1 text-left font-semibold`}>
          {children}
        </th>
      );
    },
    td({ children }) {
      return <td className={`border ${borderClass} px-2 py-1`}>{children}</td>;
    },
  };

  return (
    <div className={`break-words ${textClass} ${className}`}>
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </Markdown>
    </div>
  );
}

function CodeBlockWrapper({ children, codeClass }: { children: React.ReactNode; codeClass: string }) {
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);
  const { t } = useTranslation();

  const handleCopy = () => {
    if (preRef.current) {
      navigator.clipboard.writeText(preRef.current.innerText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="relative group my-2">
      <pre
        ref={preRef}
        className={`max-w-full overflow-x-auto rounded-lg ${codeClass} p-3 text-xs leading-relaxed`}
      >
        {children}
      </pre>
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 rounded-md bg-black/20 text-white/70 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/40 hover:text-white"
        title={t("chat.copyCode")}
      >
        {copied ? (
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        ) : (
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
        )}
      </button>
    </div>
  );
}
