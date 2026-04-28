"use client";

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
      return (
        <pre
          className={`my-2 max-w-full overflow-x-auto rounded-lg ${codeClass} p-3 text-xs leading-relaxed`}
        >
          {children}
        </pre>
      );
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
