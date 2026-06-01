"use client";

import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { formatMessageForDisplay } from "@/lib/api/chat";

/** Normalize content so single newlines render as line breaks (remark-breaks). */
export function prepareMarkdownContent(content: string): string {
  return formatMessageForDisplay(content).replace(/\r\n/g, "\n").trim();
}

const markdownComponents: Components = {
  p: ({ children }) => (
    <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="leading-relaxed">{children}</li>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-gray-900">{children}</strong>
  ),
  h1: ({ children }) => (
    <h3 className="mb-2 text-base font-semibold text-gray-900">{children}</h3>
  ),
  h2: ({ children }) => (
    <h3 className="mb-2 text-base font-semibold text-gray-900">{children}</h3>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 text-sm font-semibold text-gray-900">{children}</h3>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-brand/40 pl-3 text-gray-600 italic">
      {children}
    </blockquote>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-brand underline underline-offset-2 hover:text-serene-accent"
    >
      {children}
    </a>
  ),
};

export interface ChatMessageMarkdownProps {
  content: string;
  className?: string;
}

export function ChatMessageMarkdown({ content, className }: ChatMessageMarkdownProps) {
  return (
    <div
      className={cn(
        "text-sm leading-relaxed text-gray-700",
        "prose prose-sm max-w-none prose-p:my-0 prose-headings:my-2",
        className
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        components={markdownComponents}
      >
        {prepareMarkdownContent(content)}
      </ReactMarkdown>
    </div>
  );
}

export interface AssistantMessageBubbleProps {
  children: React.ReactNode;
  variant?: "default" | "medical" | "crisis";
  className?: string;
}

export function AssistantMessageBubble({
  children,
  variant = "default",
  className,
}: AssistantMessageBubbleProps) {
  return (
    <div
      className={cn(
        "w-full rounded-2xl border px-4 py-3 shadow-sm",
        variant === "crisis" && "border-red-200 bg-red-50/90",
        variant === "medical" && "border-sky-200/90 bg-white",
        variant === "default" && "border-brand-border bg-white",
        className
      )}
    >
      {children}
    </div>
  );
}
