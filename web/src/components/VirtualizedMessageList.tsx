"use client";

import { useRef, useEffect, useCallback } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Bot, User, Loader2, Wrench, Check, X } from "lucide-react";
import ReactMarkdown from "react-markdown";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  toolCalls?: { tool: string; success?: boolean }[];
}

interface VirtualizedMessageListProps {
  messages: Message[];
  height?: number;
}

export default function VirtualizedMessageList({
  messages,
  height,
}: VirtualizedMessageListProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const lastMessageCount = useRef(messages.length);
  const isUserScrolling = useRef(false);

  // Dynamic row height estimation based on content
  const estimateSize = useCallback(
    (index: number) => {
      const message = messages[index];
      if (!message) return 100;

      // Estimate based on content length
      const baseHeight = 80;
      const contentLength = message.content.length;
      const toolCallsHeight = (message.toolCalls?.length || 0) * 30;

      // Rough estimate: ~50 chars per line, 24px per line
      const estimatedLines = Math.ceil(contentLength / 50);
      const contentHeight = Math.min(estimatedLines * 24, 500);

      return baseHeight + contentHeight + toolCallsHeight;
    },
    [messages]
  );

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize,
    overscan: 3,
  });

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messages.length > lastMessageCount.current && !isUserScrolling.current) {
      // New message added - scroll to bottom
      virtualizer.scrollToIndex(messages.length - 1, { align: "end" });
    }
    lastMessageCount.current = messages.length;
  }, [messages.length, virtualizer]);

  // Track user scrolling
  const handleScroll = useCallback(() => {
    if (!parentRef.current) return;

    const { scrollTop, scrollHeight, clientHeight } = parentRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 100;

    // If user scrolled up, don't auto-scroll
    isUserScrolling.current = !isAtBottom;
  }, []);

  if (messages.length === 0) {
    return (
      <div
        data-testid="empty-state"
        className="flex flex-col items-center justify-center h-full p-8"
      >
        <div
          className="w-16 h-16 rounded-2xl flex items-center justify-center mb-6"
          style={{ background: "var(--bg-tertiary)" }}
        >
          <Bot size={32} style={{ color: "var(--accent-primary)" }} />
        </div>
        <h3
          className="text-xl font-semibold mb-2"
          style={{ color: "var(--text-primary)" }}
        >
          How can I help you today?
        </h3>
        <p className="text-center" style={{ color: "var(--text-muted)" }}>
          I can create trading strategies, run backtests, and analyze market data.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      data-testid="message-list"
      data-testid-scroll="scroll-container"
      role="log"
      aria-live="polite"
      onScroll={handleScroll}
      style={{
        height: height ? `${height}px` : "100%",
        overflowY: "auto",
      }}
      className="p-6"
    >
      <div
        data-testid="virtual-container"
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const message = messages[virtualRow.index];

          return (
            <div
              key={virtualRow.key}
              data-testid="message-item"
              role="article"
              data-index={virtualRow.index}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualRow.start}px)`,
              }}
              className="pb-6"
            >
              <div
                className={`flex gap-4 max-w-3xl mx-auto ${
                  message.role === "user" ? "justify-end" : ""
                }`}
              >
                {message.role === "assistant" && (
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: "var(--bg-tertiary)" }}
                  >
                    <Bot size={16} style={{ color: "var(--accent-primary)" }} />
                  </div>
                )}

                <div className="max-w-[80%]">
                  {/* Tool calls indicator */}
                  {message.toolCalls && message.toolCalls.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-2">
                      {message.toolCalls.map((tc, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs"
                          style={{
                            background: "var(--bg-tertiary)",
                            color:
                              tc.success === undefined
                                ? "var(--text-muted)"
                                : tc.success
                                ? "var(--accent-primary)"
                                : "var(--accent-danger)",
                          }}
                        >
                          <Wrench size={10} />
                          {tc.tool}
                          {tc.success !== undefined &&
                            (tc.success ? <Check size={10} /> : <X size={10} />)}
                        </span>
                      ))}
                    </div>
                  )}

                  <div
                    className={`rounded-lg px-4 py-3 ${
                      message.role === "user" ? "glow-border" : ""
                    }`}
                    style={{
                      background:
                        message.role === "user"
                          ? "var(--accent-primary)"
                          : "var(--bg-secondary)",
                      color:
                        message.role === "user"
                          ? "var(--bg-primary)"
                          : "var(--text-primary)",
                    }}
                  >
                    {message.content ? (
                      message.role === "assistant" ? (
                        <div className="markdown-content">
                          <ReactMarkdown
                            components={{
                              h1: ({ children }) => (
                                <h1
                                  className="text-xl font-bold mt-4 mb-2"
                                  style={{ color: "var(--text-primary)" }}
                                >
                                  {children}
                                </h1>
                              ),
                              h2: ({ children }) => (
                                <h2
                                  className="text-lg font-semibold mt-4 mb-2"
                                  style={{ color: "var(--text-primary)" }}
                                >
                                  {children}
                                </h2>
                              ),
                              h3: ({ children }) => (
                                <h3
                                  className="text-base font-semibold mt-3 mb-1"
                                  style={{ color: "var(--text-primary)" }}
                                >
                                  {children}
                                </h3>
                              ),
                              p: ({ children }) => (
                                <p className="mb-3 leading-relaxed">{children}</p>
                              ),
                              ul: ({ children }) => (
                                <ul className="list-disc list-inside mb-3 space-y-1">
                                  {children}
                                </ul>
                              ),
                              ol: ({ children }) => (
                                <ol className="list-decimal list-inside mb-3 space-y-1">
                                  {children}
                                </ol>
                              ),
                              li: ({ children }) => (
                                <li className="ml-2">{children}</li>
                              ),
                              strong: ({ children }) => (
                                <strong style={{ color: "var(--accent-primary)" }}>
                                  {children}
                                </strong>
                              ),
                              code: ({ children }) => (
                                <code
                                  className="px-1.5 py-0.5 rounded text-sm"
                                  style={{ background: "var(--bg-tertiary)" }}
                                >
                                  {children}
                                </code>
                              ),
                              pre: ({ children }) => (
                                <pre
                                  className="p-3 rounded-lg mb-3"
                                  style={{
                                    background: "var(--bg-tertiary)",
                                    overflowX: "auto",
                                  }}
                                >
                                  {children}
                                </pre>
                              ),
                            }}
                          >
                            {message.content}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <div className="whitespace-pre-wrap">{message.content}</div>
                      )
                    ) : (
                      <span className="flex items-center gap-2">
                        <Loader2
                          size={16}
                          className="animate-spin"
                          style={{ color: "var(--text-muted)" }}
                        />
                        <span style={{ color: "var(--text-muted)" }}>Thinking...</span>
                      </span>
                    )}
                  </div>
                </div>

                {message.role === "user" && (
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: "var(--bg-tertiary)" }}
                  >
                    <User size={16} style={{ color: "var(--text-secondary)" }} />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
