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

  const textClass = inverse ? "text-on-accent" : "text-text-primary";
  const mutedClass = inverse ? "text-on-accent/70" : "text-text-secondary";
  const borderClass = inverse ? "border-on-accent/20" : "border-border-default";
  const codeClass = inverse
    ? "bg-on-accent/10 text-on-accent"
    : "bg-surface-secondary text-text-charcoal";
  const linkClass = inverse
    ? "text-primary-200 hover:text-on-accent"
    : "text-brand-blue hover:underline";

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
      return <h1 className="mb-2 mt-4 text-xl font-semibold leading-snug first:mt-0">{children}</h1>;
    },
    h2({ children }) {
      return <h2 className="mb-2 mt-4 text-lg font-semibold leading-snug first:mt-0">{children}</h2>;
    },
    h3({ children }) {
      return <h3 className="mb-1.5 mt-3 text-base font-semibold leading-snug first:mt-0">{children}</h3>;
    },
    h4({ children }) {
      return <h4 className="mb-1.5 mt-3 font-semibold leading-snug first:mt-0">{children}</h4>;
    },
    hr() {
      return <hr className={`my-3 border-0 border-t ${borderClass}`} />;
    },
    pre({ children }) {
      return <CodeBlockWrapper codeClass={codeClass} borderClass={borderClass}>{children}</CodeBlockWrapper>;
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
          <table className={`w-full border-collapse text-[13px] leading-normal ${textClass}`}>
            {children}
          </table>
        </div>
      );
    },
    th({ children }) {
      return (
        <th className={`border ${borderClass} ${inverse ? "" : "bg-surface-secondary"} px-2.5 py-1.5 text-left font-semibold`}>
          {children}
        </th>
      );
    },
    td({ children }) {
      return <td className={`border ${borderClass} px-2.5 py-1.5 align-top`}>{children}</td>;
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

function CodeBlockWrapper({ children, codeClass, borderClass }: { children: React.ReactNode; codeClass: string; borderClass: string }) {
  const preRef = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);
  const { t } = useTranslation();

  const handleCopy = () => {
    if (!preRef.current) return;
    void navigator.clipboard
      .writeText(preRef.current.innerText)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => setCopied(false));
  };

  return (
    <div className="relative group my-2">
      <pre
        ref={preRef}
        className={`max-w-full overflow-x-auto rounded-lg border ${borderClass} ${codeClass} p-3 pr-11 text-[13px] leading-relaxed [&>code]:rounded-none [&>code]:bg-transparent [&>code]:p-0 [&>code]:text-[1em]`}
      >
        {children}
      </pre>
      <button
        type="button"
        onClick={handleCopy}
        className="absolute right-2 top-2 rounded-md border border-border-light bg-surface-primary p-1.5 text-text-muted opacity-0 transition-opacity hover:text-text-primary focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
        title={copied ? t("common.copySuccess") : t("chat.copyCode")}
        aria-label={copied ? t("common.copySuccess") : t("chat.copyCode")}
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
