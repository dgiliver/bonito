"use client";

import { useState } from "react";
import {
  AnalysisProvider,
  useAnalysis,
  ChartContextPayload,
  BacktestResult,
} from "@/contexts/AnalysisContext";
import { TradingProvider, useTrading } from "@/contexts/TradingContext";
import { DeploymentModal, AccountLinkingModal } from "@/components/trading";
import { streamChat, ChatEvent } from "@/lib/api";
import {
  Send,
  Bot,
  User,
  Loader2,
  MessageSquare,
  TrendingUp,
  Info,
  X,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Save,
  Trash2,
  RotateCcw,
  List,
  Rocket,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import dynamic from "next/dynamic";

// Dynamically import chart to avoid SSR issues
// Using V2 with multi-chart architecture for proper panel scales
const IntelligentChart = dynamic(
  () => import("./IntelligentChartV2").then((m) => m.IntelligentChartV2),
  {
  ssr: false,
  loading: () => (
    <div
      className="flex items-center justify-center h-full"
      style={{ background: "var(--bg-primary)" }}
    >
      <Loader2
        className="animate-spin"
        style={{ color: "var(--text-muted)" }}
      />
    </div>
  ),
});

// ============================================================================
// Message Types
// ============================================================================

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  toolCalls?: { tool: string; success?: boolean }[];
  chartContext?: ChartContextPayload;
}

// ============================================================================
// Context-Aware Chat Panel
// ============================================================================

function ChatPanel() {
  const { state, getChartContext, dispatch, addAgentIntent } = useAnalysis();
  const {
    openDeploymentModal,
    state: tradingState,
    linkAccount,
  } = useTrading();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [showLinkAccountModal, setShowLinkAccountModal] = useState(false);

  // Check if strategy can be deployed
  const canDeploy =
    state.strategy &&
    state.backtest.result &&
    state.backtest.result.performance.total_return > 0 &&
    tradingState.account.linked;

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isLoading) return;

    // Get current chart context
    const chartContext = getChartContext();

    // Enhance message with context indicator
    const contextNote = chartContext.symbol
      ? `[Viewing ${chartContext.symbol} ${chartContext.interval}${chartContext.activeStrategy ? `, strategy: ${chartContext.activeStrategy}` : ""}]`
      : "";

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
      chartContext,
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

    // Include context in the message to the API
    const messageWithContext = chartContext.symbol
      ? `${contextNote}\n\n${userMessage.content}`
      : userMessage.content;

    const newSessionId = await streamChat(
      messageWithContext,
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
              // Handle chart-related tool calls
              if (event.tool === "add_indicator") {
                // Agent wants to add indicator - we'll implement this
              }
              return {
                ...m,
                toolCalls: [...(m.toolCalls || []), { tool: event.tool }],
              };
            } else if (event.type === "tool_result") {
              // Handle backtest results - defer dispatch to avoid React warning
              if (
                event.tool === "run_backtest" &&
                event.success &&
                event.data
              ) {
                const result = event.data as BacktestResult;
                if (result.strategy_name && result.trades) {
                  // Defer to avoid "cannot update during render" error
                  setTimeout(() => {
                    dispatch({ type: "SET_BACKTEST_RESULT", result });
                    // Note: Chart will show trades based on current visible data
                    // User can adjust range to see all trades
                  }, 0);
                }
              }

              // Handle chart_control tool results - dispatch intents to chart
              if (
                event.tool === "chart_control" &&
                event.success &&
                event.data
              ) {
                const toolData = event.data as {
                  intent?: Record<string, unknown>;
                  message?: string;
                };
                if (toolData.intent) {
                  console.log(
                    "[ChatPanel] Dispatching chart intent:",
                    toolData.intent,
                  );
                  // Defer to avoid "cannot update during render" error
                  setTimeout(() => {
                    addAgentIntent(
                      toolData.intent as Parameters<typeof addAgentIntent>[0],
                    );
                  }, 0);
                }
              }
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

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="absolute right-0 top-1/2 -translate-y-1/2 p-2 rounded-l-lg shadow-lg z-10"
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-color)",
        }}
      >
        <ChevronLeft size={16} style={{ color: "var(--text-muted)" }} />
      </button>
    );
  }

  return (
    <div
      className="w-96 border-l flex flex-col h-full"
      style={{
        borderColor: "var(--border-color)",
        background: "var(--bg-primary)",
      }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 border-b flex items-center justify-between"
        style={{ borderColor: "var(--border-color)" }}
      >
        <div className="flex items-center gap-2">
          <Bot size={18} style={{ color: "var(--accent-primary)" }} />
          <span
            className="font-medium"
            style={{ color: "var(--text-primary)" }}
          >
            Analysis Assistant
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="text-xs px-2 py-0.5 rounded"
            style={{
              background: "var(--bg-tertiary)",
              color: "var(--text-muted)",
            }}
          >
            {state.chart.symbol}
          </span>
          <button
            onClick={() => setCollapsed(true)}
            className="p-1 rounded hover:bg-[var(--bg-secondary)]"
          >
            <ChevronRight size={14} style={{ color: "var(--text-muted)" }} />
          </button>
        </div>
      </div>

      {/* Context Bar - Strategy Info */}
      {state.strategy && (
        <div
          className="px-3 py-2 border-b flex items-center gap-2 text-xs"
          style={{
            borderColor: "var(--border-color)",
            background: "var(--bg-secondary)",
          }}
        >
          <Sparkles size={12} style={{ color: "var(--accent-primary)" }} />
          <span style={{ color: "var(--text-muted)" }}>Strategy:</span>
          <span style={{ color: "var(--text-primary)" }}>
            {state.strategy.name}
          </span>
        </div>
      )}

      {/* Performance Bar - Buy & Hold Comparison */}
      {state.backtest.result && (
        <div
          className="px-3 py-2 border-b flex items-center justify-between text-xs"
          style={{
            borderColor: "var(--border-color)",
            background: "var(--bg-tertiary)",
          }}
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
              <TrendingUp
                size={12}
                style={{ color: "var(--accent-primary)" }}
              />
              <span style={{ color: "var(--text-muted)" }}>Strategy:</span>
              <span
                style={{
                  color:
                    state.backtest.result.performance.total_return >= 0
                      ? "var(--accent-success)"
                      : "var(--accent-danger)",
                }}
              >
                {state.backtest.result.performance.total_return >= 0 ? "+" : ""}
                {state.backtest.result.performance.total_return.toFixed(1)}%
              </span>
            </div>
            {state.backtest.result.performance.buy_hold_return !==
              undefined && (
              <>
                <span style={{ color: "var(--text-muted)" }}>|</span>
                <div className="flex items-center gap-1">
                  <span style={{ color: "var(--text-muted)" }}>
                    Buy & Hold:
                  </span>
                  <span
                    style={{
                      color:
                        state.backtest.result.performance.buy_hold_return >= 0
                          ? "var(--accent-success)"
                          : "var(--accent-danger)",
                    }}
                  >
                    {state.backtest.result.performance.buy_hold_return >= 0
                      ? "+"
                      : ""}
                    {state.backtest.result.performance.buy_hold_return.toFixed(
                      1,
                    )}
                    %
                  </span>
                </div>
              </>
            )}
          </div>
          {state.backtest.result.performance.alpha !== undefined && (
            <div
              className="px-2 py-0.5 rounded text-xs font-medium"
              style={{
                background:
                  state.backtest.result.performance.alpha >= 0
                    ? "rgba(34, 197, 94, 0.1)"
                    : "rgba(239, 68, 68, 0.1)",
                color:
                  state.backtest.result.performance.alpha >= 0
                    ? "var(--accent-success)"
                    : "var(--accent-danger)",
              }}
            >
              α {state.backtest.result.performance.alpha >= 0 ? "+" : ""}
              {state.backtest.result.performance.alpha.toFixed(1)}%
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center px-4">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center mb-4"
              style={{ background: "var(--bg-tertiary)" }}
            >
              <MessageSquare
                size={24}
                style={{ color: "var(--accent-primary)" }}
              />
            </div>
            <p
              className="font-medium mb-2"
              style={{ color: "var(--text-primary)" }}
            >
              Context-Aware Analysis
            </p>
            <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
              I can see what you&apos;re viewing. Ask about the chart, create
              strategies, or click trades to learn more.
            </p>
            <div className="space-y-2 w-full">
              {[
                "What's the trend on this chart?",
                "Create a momentum strategy",
                "Explain the recent price action",
              ].map((suggestion, i) => (
                <button
                  key={i}
                  onClick={() => setInput(suggestion)}
                  className="w-full text-left text-sm p-2 rounded-lg hover:bg-[var(--bg-secondary)] transition-colors"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-3 ${message.role === "user" ? "flex-row-reverse" : ""}`}
            >
              <div
                className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ background: "var(--bg-tertiary)" }}
              >
                {message.role === "user" ? (
                  <User size={14} style={{ color: "var(--text-secondary)" }} />
                ) : (
                  <Bot size={14} style={{ color: "var(--accent-primary)" }} />
                )}
              </div>
              <div className="max-w-[85%]">
                {/* Tool calls */}
                {message.toolCalls && message.toolCalls.length > 0 && (
                  <div
                    className={`flex flex-wrap gap-1 mb-1 ${message.role === "user" ? "justify-end" : ""}`}
                  >
                    {message.toolCalls.map((tc, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs"
                        style={{
                          background: "var(--bg-tertiary)",
                          color:
                            tc.success === undefined
                              ? "var(--text-muted)"
                              : tc.success
                                ? "var(--accent-success)"
                                : "var(--accent-danger)",
                        }}
                      >
                        {tc.tool}
                      </span>
                    ))}
                  </div>
                )}
                <div
                  className="rounded-lg px-3 py-2 text-sm"
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
                      <div className="text-left">
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => (
                              <p className="mb-2 last:mb-0 leading-relaxed">
                                {children}
                              </p>
                            ),
                            strong: ({ children }) => (
                              <strong
                                style={{ color: "var(--accent-primary)" }}
                              >
                                {children}
                              </strong>
                            ),
                            ul: ({ children }) => (
                              <ul className="list-disc list-inside mb-2 space-y-1">
                                {children}
                              </ul>
                            ),
                            ol: ({ children }) => (
                              <ol className="list-decimal list-inside mb-2 space-y-1">
                                {children}
                              </ol>
                            ),
                            li: ({ children }) => (
                              <li className="leading-relaxed">{children}</li>
                            ),
                            code: ({ children }) => (
                              <code
                                className="px-1 py-0.5 rounded text-xs"
                                style={{ background: "var(--bg-tertiary)" }}
                              >
                                {children}
                              </code>
                            ),
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <span className="text-left">{message.content}</span>
                    )
                  ) : (
                    <Loader2
                      size={14}
                      className="animate-spin"
                      style={{ color: "var(--text-muted)" }}
                    />
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Input */}
      <div
        className="p-3 border-t"
        style={{ borderColor: "var(--border-color)" }}
      >
        <form onSubmit={handleSubmit}>
          <div
            className="flex items-end gap-2 p-2 rounded-lg"
            style={{ background: "var(--bg-secondary)" }}
          >
            <textarea
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask about the chart..."
              rows={1}
              className="flex-1 resize-none bg-transparent border-none outline-none text-sm"
              style={{
                color: "var(--text-primary)",
                minHeight: "20px",
                maxHeight: "120px",
              }}
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="p-2 rounded-lg"
              style={{
                background:
                  input.trim() && !isLoading
                    ? "var(--accent-primary)"
                    : "transparent",
                color:
                  input.trim() && !isLoading
                    ? "var(--bg-primary)"
                    : "var(--text-muted)",
                opacity: !input.trim() || isLoading ? 0.5 : 1,
              }}
            >
              {isLoading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Send size={16} />
              )}
            </button>
          </div>
        </form>

        {/* Quick Actions */}
        {(messages.length > 0 || state.backtest.result) && (
          <div className="flex flex-wrap gap-2 mt-2">
            {/* Save Strategy - show if there's a strategy */}
            {state.strategy && (
              <button
                onClick={() => {
                  setInput(`Save the strategy "${state.strategy?.name}"`);
                  setTimeout(
                    () => document.querySelector("form")?.requestSubmit(),
                    100,
                  );
                }}
                disabled={isLoading}
                className="flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors hover:bg-[var(--bg-tertiary)]"
                style={{
                  color: "var(--text-muted)",
                  border: "1px solid var(--border-color)",
                  opacity: isLoading ? 0.5 : 1,
                }}
              >
                <Save size={12} />
                Save Strategy
              </button>
            )}

            {/* Deploy to Bot - show if strategy has positive backtest and account is linked */}
            {canDeploy && state.strategy && (
              <button
                onClick={() => {
                  openDeploymentModal({
                    strategy_name: state.strategy!.name,
                    strategy_config: { ...state.strategy! },
                  });
                }}
                disabled={isLoading}
                className="flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors"
                style={{
                  background: "var(--accent-primary)",
                  color: "var(--bg-primary)",
                  opacity: isLoading ? 0.5 : 1,
                }}
              >
                <Rocket size={12} />
                Deploy to Bot
              </button>
            )}

            {/* Link Account prompt - show if strategy exists but no account linked */}
            {state.strategy &&
              state.backtest.result &&
              !tradingState.account.linked && (
                <button
                  onClick={() => setShowLinkAccountModal(true)}
                  disabled={isLoading}
                  className="flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors"
                  style={{
                    background: "var(--accent-primary)",
                    color: "var(--bg-primary)",
                    opacity: isLoading ? 0.5 : 1,
                  }}
                  title="Link Alpaca account to deploy bots"
                >
                  <Rocket size={12} />
                  Link Account to Deploy
                </button>
              )}

            {/* View Trades - show if there's a backtest */}
            {state.backtest.result &&
              state.backtest.result.trades.length > 0 && (
                <button
                  onClick={() => {
                    dispatch({
                      type: "SET_SIDE_PANEL",
                      panel: "trade-details",
                    });
                    // Select first trade to show details
                    if (state.backtest.result?.trades[0]) {
                      dispatch({
                        type: "SELECT_TRADE",
                        trade: state.backtest.result.trades[0],
                      });
                    }
                  }}
                  disabled={isLoading}
                  className="flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors hover:bg-[var(--bg-tertiary)]"
                  style={{
                    color: "var(--text-muted)",
                    border: "1px solid var(--border-color)",
                    opacity: isLoading ? 0.5 : 1,
                  }}
                >
                  <List size={12} />
                  View Trades ({state.backtest.result.trades.length})
                </button>
              )}

            {/* Clear Chart - show if there's backtest markers */}
            {state.backtest.result && (
              <button
                onClick={() => {
                  dispatch({ type: "SET_BACKTEST_RESULT", result: null });
                  dispatch({ type: "CLEAR_ANNOTATIONS" });
                }}
                disabled={isLoading}
                className="flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors hover:bg-[var(--bg-tertiary)]"
                style={{
                  color: "var(--text-muted)",
                  border: "1px solid var(--border-color)",
                  opacity: isLoading ? 0.5 : 1,
                }}
              >
                <Trash2 size={12} />
                Clear Chart
              </button>
            )}

            {/* New Chat - always show if there are messages */}
            {messages.length > 0 && (
              <button
                onClick={() => {
                  setMessages([]);
                  setSessionId(null);
                }}
                disabled={isLoading}
                className="flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors hover:bg-[var(--bg-tertiary)]"
                style={{
                  color: "var(--text-muted)",
                  border: "1px solid var(--border-color)",
                  opacity: isLoading ? 0.5 : 1,
                }}
              >
                <RotateCcw size={12} />
                New Chat
              </button>
            )}
          </div>
        )}
      </div>

      {/* Account Linking Modal */}
      <AccountLinkingModal
        isOpen={showLinkAccountModal}
        onClose={() => setShowLinkAccountModal(false)}
        onLink={linkAccount}
      />
    </div>
  );
}

// ============================================================================
// Trade Details Panel
// ============================================================================

function TradeDetailsPanel() {
  const { state, dispatch } = useAnalysis();
  const trade = state.backtest.selectedTrade;
  const trades = state.backtest.result?.trades || [];
  const currentIndex = trade ? trades.findIndex((t) => t.id === trade.id) : -1;
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < trades.length - 1;

  const goToPrev = () => {
    if (hasPrev) {
      dispatch({ type: "SELECT_TRADE", trade: trades[currentIndex - 1] });
    }
  };

  const goToNext = () => {
    if (hasNext) {
      dispatch({ type: "SELECT_TRADE", trade: trades[currentIndex + 1] });
    }
  };

  if (!trade) {
    return (
      <div
        className="w-80 border-l flex flex-col items-center justify-center p-6"
        style={{
          borderColor: "var(--border-color)",
          background: "var(--bg-secondary)",
        }}
      >
        <Info
          size={32}
          style={{ color: "var(--text-muted)" }}
          className="mb-3 opacity-50"
        />
        <p
          className="text-sm text-center"
          style={{ color: "var(--text-muted)" }}
        >
          Click a trade marker on the chart to see details
        </p>
      </div>
    );
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div
      className="w-80 border-l flex flex-col"
      style={{
        borderColor: "var(--border-color)",
        background: "var(--bg-secondary)",
      }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 border-b flex items-center justify-between"
        style={{ borderColor: "var(--border-color)" }}
      >
        <span className="font-medium" style={{ color: "var(--text-primary)" }}>
          Trade Details
        </span>
        <div className="flex items-center gap-1">
          {/* Trade Navigation */}
          <span className="text-xs mr-2" style={{ color: "var(--text-muted)" }}>
            {currentIndex + 1} / {trades.length}
          </span>
          <button
            onClick={goToPrev}
            disabled={!hasPrev}
            className="p-1 rounded hover:bg-[var(--bg-tertiary)] disabled:opacity-30"
          >
            <ChevronLeft size={14} style={{ color: "var(--text-muted)" }} />
          </button>
          <button
            onClick={goToNext}
            disabled={!hasNext}
            className="p-1 rounded hover:bg-[var(--bg-tertiary)] disabled:opacity-30"
          >
            <ChevronRight size={14} style={{ color: "var(--text-muted)" }} />
          </button>
          <button
            onClick={() => {
              dispatch({ type: "SELECT_TRADE", trade: null });
              dispatch({ type: "SET_SIDE_PANEL", panel: "chat" });
            }}
            className="p-1 rounded hover:bg-[var(--bg-tertiary)] ml-1"
          >
            <X size={14} style={{ color: "var(--text-muted)" }} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 p-4 space-y-4 overflow-y-auto">
        {/* P&L */}
        <div className="text-center py-3">
          <p
            className="text-3xl font-bold"
            style={{
              color:
                trade.pnl >= 0
                  ? "var(--accent-success)"
                  : "var(--accent-danger)",
            }}
          >
            {trade.pnl >= 0 ? "+" : ""}$
            {trade.pnl.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </p>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {trade.pnl_percent >= 0 ? "+" : ""}
            {trade.pnl_percent.toFixed(2)}%
          </p>
        </div>

        {/* Details Grid */}
        <div className="space-y-3">
          <div className="flex justify-between text-sm">
            <span style={{ color: "var(--text-muted)" }}>Side</span>
            <span
              className="font-medium"
              style={{
                color:
                  trade.position_side === "short"
                    ? "var(--accent-danger)"
                    : "var(--accent-success)",
              }}
            >
              {(trade.position_side || "long").toUpperCase()}
            </span>
          </div>

          <div className="flex justify-between text-sm">
            <span style={{ color: "var(--text-muted)" }}>Entry</span>
            <div className="text-right">
              <p style={{ color: "var(--text-primary)" }}>
                ${trade.entry_price.toFixed(2)}
              </p>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                {formatDate(trade.entry_time)}
              </p>
            </div>
          </div>

          <div className="flex justify-between text-sm">
            <span style={{ color: "var(--text-muted)" }}>Exit</span>
            <div className="text-right">
              <p style={{ color: "var(--text-primary)" }}>
                ${trade.exit_price.toFixed(2)}
              </p>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                {formatDate(trade.exit_time)}
              </p>
            </div>
          </div>

          <div className="flex justify-between text-sm">
            <span style={{ color: "var(--text-muted)" }}>Quantity</span>
            <span style={{ color: "var(--text-primary)" }}>
              {trade.quantity >= 1
                ? trade.quantity.toFixed(2)
                : trade.quantity.toFixed(4)}
            </span>
          </div>

          <div className="flex justify-between text-sm">
            <span style={{ color: "var(--text-muted)" }}>Exit Reason</span>
            <span
              className="px-2 py-0.5 rounded text-xs"
              style={{
                background: "var(--bg-tertiary)",
                color: trade.exit_reason.includes("stop")
                  ? "var(--accent-danger)"
                  : "var(--accent-primary)",
              }}
            >
              {trade.exit_reason}
            </span>
          </div>
        </div>

        {/* Duration */}
        <div
          className="p-3 rounded-lg"
          style={{ background: "var(--bg-tertiary)" }}
        >
          <p className="text-xs mb-1" style={{ color: "var(--text-muted)" }}>
            Duration
          </p>
          <p className="font-medium" style={{ color: "var(--text-primary)" }}>
            {Math.ceil(
              (new Date(trade.exit_time).getTime() -
                new Date(trade.entry_time).getTime()) /
                (1000 * 60 * 60 * 24),
            )}{" "}
            days
          </p>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Main Analysis View
// ============================================================================

function AnalysisContent() {
  const { state } = useAnalysis();

  // Show trade details if a trade is selected, otherwise show chat
  const showTradeDetails =
    state.ui.sidePanel === "trade-details" && state.backtest.selectedTrade;

  return (
    <div className="flex h-full" style={{ background: "var(--bg-primary)" }}>
      {/* Main Chart Area */}
      <div className="flex-1 min-w-0">
        <IntelligentChart />
      </div>

      {/* Side Panels - both rendered to preserve state, one hidden */}
      <div className={showTradeDetails ? "hidden" : "contents"}>
        <ChatPanel />
      </div>
      <div className={showTradeDetails ? "contents" : "hidden"}>
        <TradeDetailsPanel />
      </div>
    </div>
  );
}

export function AnalysisView() {
  return (
    <TradingProvider>
      <AnalysisProvider>
        <AnalysisContent />
        <DeploymentModal />
      </AnalysisProvider>
    </TradingProvider>
  );
}
