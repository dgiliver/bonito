"use client";

import { useRef, useEffect, useState } from "react";
import {
  Send,
  Bot,
  User,
  Loader2,
  Sparkles,
  Wrench,
  Check,
  X,
  Save,
  Play,
  RotateCcw,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { streamChat, ChatEvent } from "@/lib/api";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  toolCalls?: { tool: string; success?: boolean }[];
}

interface ChatProps {
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  sessionId: string | null;
  setSessionId: React.Dispatch<React.SetStateAction<string | null>>;
}

const suggestions = [
  "Create an RSI momentum strategy with a 200-day SMA trend filter",
  "Backtest my saved strategies on SPY for the last year",
  "What data do I have available?",
  "Compare EMA cross and RSI strategies on QQQ",
];

export default function Chat({
  messages,
  setMessages,
  sessionId,
  setSessionId,
}: ChatProps) {
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Auto-resize textarea based on content
  useEffect(() => {
    const textarea = inputRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
    }
  }, [input]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        toolCalls: [],
      },
    ]);

    const newSessionId = await streamChat(
      userMessage.content,
      sessionId,
      (event: ChatEvent) => {
        if (event.type === "done") {
          setIsLoading(false);
          return;
        }

        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== assistantId) return m;

            if (event.type === "tool_call") {
              return {
                ...m,
                toolCalls: [...(m.toolCalls || []), { tool: event.tool }],
              };
            } else if (event.type === "tool_result") {
              return {
                ...m,
                toolCalls: m.toolCalls?.map((tc) =>
                  tc.tool === event.tool
                    ? { ...tc, success: event.success }
                    : tc,
                ),
              };
            } else if (event.type === "response") {
              return { ...m, content: event.content };
            }
            return m;
          }),
        );
      },
      (error) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: `Error: ${error}` } : m,
          ),
        );
        setIsLoading(false);
      },
    );

    if (newSessionId) {
      setSessionId(newSessionId);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSuggestion = (suggestion: string) => {
    setInput(suggestion);
    inputRef.current?.focus();
  };

  const sendQuickAction = (message: string) => {
    if (isLoading) return;
    setInput(message);
    // Auto-submit after a brief delay to show what's being sent
    setTimeout(() => {
      const form = document.querySelector("form");
      form?.requestSubmit();
    }, 100);
  };

  // Check if there's been any strategy-related activity
  const hasStrategyActivity = messages.some(
    (m) =>
      m.role === "assistant" &&
      m.toolCalls?.some((tc) => tc.tool === "create_strategy" && tc.success),
  );

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Header */}
      <header
        className="px-6 py-4 border-b flex items-center justify-between"
        style={{ borderColor: "var(--border-color)" }}
      >
        <div>
          <h2
            className="text-lg font-semibold"
            style={{ color: "var(--text-primary)" }}
          >
            AI Trading Agent
          </h2>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Create and backtest trading strategies with natural language
          </p>
        </div>
        <div className="flex items-center gap-2">
          {sessionId && (
            <span
              className="badge text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              Session: {sessionId}
            </span>
          )}
          <span
            className="badge"
            style={{
              background: "rgba(62, 207, 142, 0.15)",
              color: "var(--accent-primary)",
            }}
          >
            <Sparkles size={12} className="mr-1" />
            Claude 3.5 Sonnet
          </span>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center">
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
            <p
              className="text-center max-w-md mb-8"
              style={{ color: "var(--text-muted)" }}
            >
              I can create trading strategies, run backtests, and analyze market
              data. Try one of these:
            </p>
            <div className="grid grid-cols-2 gap-3 max-w-2xl">
              {suggestions.map((suggestion, i) => (
                <button
                  key={i}
                  onClick={() => handleSuggestion(suggestion)}
                  className="card card-hover p-4 text-left text-sm transition-all"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-4 animate-slide-up ${
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
                            (tc.success ? (
                              <Check size={10} />
                            ) : (
                              <X size={10} />
                            ))}
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
                                <p className="mb-3 leading-relaxed">
                                  {children}
                                </p>
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
                                <strong
                                  style={{ color: "var(--accent-primary)" }}
                                >
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
                                  className="p-3 rounded-lg overflow-x-auto mb-3"
                                  style={{ background: "var(--bg-tertiary)" }}
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
                        <div className="whitespace-pre-wrap">
                          {message.content}
                        </div>
                      )
                    ) : (
                      <span className="flex items-center gap-2">
                        <Loader2
                          size={16}
                          className="animate-spin"
                          style={{ color: "var(--text-muted)" }}
                        />
                        <span style={{ color: "var(--text-muted)" }}>
                          Thinking...
                        </span>
                      </span>
                    )}
                  </div>
                </div>
                {message.role === "user" && (
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: "var(--bg-tertiary)" }}
                  >
                    <User
                      size={16}
                      style={{ color: "var(--text-secondary)" }}
                    />
                  </div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div
        className="p-4 border-t"
        style={{ borderColor: "var(--border-color)" }}
      >
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div
            className="flex items-end gap-3 p-3 rounded-xl glow-border"
            style={{ background: "var(--bg-secondary)" }}
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Create a strategy, run a backtest, or ask about your data..."
              rows={1}
              className="flex-1 resize-none bg-transparent border-none outline-none overflow-y-auto"
              style={{
                color: "var(--text-primary)",
                minHeight: "24px",
                maxHeight: "120px",
                lineHeight: "1.5",
              }}
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="btn btn-primary p-2.5"
              style={{
                opacity: !input.trim() || isLoading ? 0.5 : 1,
                cursor: !input.trim() || isLoading ? "not-allowed" : "pointer",
              }}
            >
              {isLoading ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <Send size={18} />
              )}
            </button>
          </div>
          <p
            className="text-xs text-center mt-2"
            style={{ color: "var(--text-muted)" }}
          >
            Press Enter to send, Shift+Enter for new line
          </p>

          {/* Quick Actions */}
          {messages.length > 0 && (
            <div className="flex items-center justify-center gap-2 mt-3">
              {hasStrategyActivity && (
                <>
                  <button
                    onClick={() => sendQuickAction("Save this strategy")}
                    disabled={isLoading}
                    className="btn btn-ghost px-3 py-1.5 text-xs flex items-center gap-1.5"
                    style={{
                      border: "1px solid var(--border-color)",
                      opacity: isLoading ? 0.5 : 1,
                    }}
                  >
                    <Save size={12} />
                    Save Strategy
                  </button>
                  <button
                    onClick={() =>
                      sendQuickAction("Run a backtest on this strategy")
                    }
                    disabled={isLoading}
                    className="btn btn-ghost px-3 py-1.5 text-xs flex items-center gap-1.5"
                    style={{
                      border: "1px solid var(--border-color)",
                      opacity: isLoading ? 0.5 : 1,
                    }}
                  >
                    <Play size={12} />
                    Run Backtest
                  </button>
                </>
              )}
              <button
                onClick={() => {
                  setMessages([]);
                  setSessionId(null);
                }}
                disabled={isLoading}
                className="btn btn-ghost px-3 py-1.5 text-xs flex items-center gap-1.5"
                style={{
                  border: "1px solid var(--border-color)",
                  opacity: isLoading ? 0.5 : 1,
                }}
              >
                <RotateCcw size={12} />
                New Chat
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
