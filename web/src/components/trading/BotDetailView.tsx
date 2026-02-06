"use client";

import { useState, useEffect } from "react";
import { DeployedBot } from "@/contexts/TradingContext";
import { Position, Order } from "@/types/trading";
import {
  X,
  Bot,
  Activity,
  TrendingUp,
  TrendingDown,
  Pause,
  Play,
  Square,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { TradeHistory } from "./TradeHistory";

interface BotDetailViewProps {
  bot: DeployedBot;
  isOpen: boolean;
  onClose: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}

interface BotDetailData {
  bot: DeployedBot;
  positions: Position[];
  pending_orders: Order[];
  performance: {
    total_trades: number;
    realized_pnl: number;
    unrealized_pnl: number;
    daily_pnl: number;
    current_equity: number;
  };
  risk: {
    score: "low" | "medium" | "high" | "extreme";
    warnings: string[];
  };
  start_time: string;
}

export function BotDetailView({
  bot,
  isOpen,
  onClose,
  onPause,
  onResume,
  onStop,
}: BotDetailViewProps) {
  const [detailData, setDetailData] = useState<BotDetailData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPositions, setShowPositions] = useState(true);
  const [showOrders, setShowOrders] = useState(true);

  useEffect(() => {
    if (!isOpen) return;

    const fetchDetails = async () => {
      try {
        const response = await fetch(`/api/trading/bots/${bot.id}`);
        if (!response.ok) throw new Error("Failed to fetch bot details");
        const data = await response.json();
        setDetailData(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load details");
      } finally {
        setIsLoading(false);
      }
    };

    fetchDetails();
    const interval = setInterval(fetchDetails, 5000);
    return () => clearInterval(interval);
  }, [isOpen, bot.id]);

  if (!isOpen) return null;

  const statusConfig = {
    running: {
      color: "var(--accent-success)",
      label: "Running",
      bg: "rgba(34, 197, 94, 0.1)",
    },
    paused: {
      color: "var(--accent-warning)",
      label: "Paused",
      bg: "rgba(234, 179, 8, 0.1)",
    },
    stopped: {
      color: "var(--text-muted)",
      label: "Stopped",
      bg: "var(--bg-tertiary)",
    },
    error: {
      color: "var(--accent-danger)",
      label: "Error",
      bg: "rgba(239, 68, 68, 0.1)",
    },
  };

  const status = statusConfig[bot.status] || statusConfig.stopped;
  const totalPnl = bot.realized_pnl + bot.unrealized_pnl;
  const isProfitable = totalPnl >= 0;

  const riskScoreColors = {
    low: { bg: "rgba(34, 197, 94, 0.1)", text: "var(--accent-success)" },
    medium: { bg: "rgba(234, 179, 8, 0.1)", text: "var(--accent-warning)" },
    high: { bg: "rgba(249, 115, 22, 0.1)", text: "#f97316" },
    extreme: { bg: "rgba(239, 68, 68, 0.1)", text: "var(--accent-danger)" },
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0, 0, 0, 0.6)" }}
    >
      <div
        className="w-full max-w-4xl max-h-[90vh] rounded-xl shadow-2xl mx-4 flex flex-col"
        style={{ background: "var(--bg-primary)" }}
      >
        {/* Header */}
        <div
          className="px-6 py-4 border-b flex items-center justify-between flex-shrink-0"
          style={{ borderColor: "var(--border-color)" }}
        >
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-lg flex items-center justify-center"
              style={{ background: "var(--bg-tertiary)" }}
            >
              <Bot size={20} style={{ color: "var(--accent-primary)" }} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2
                  className="text-lg font-semibold"
                  style={{ color: "var(--text-primary)" }}
                >
                  {bot.name}
                </h2>
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ background: status.color }}
                />
                <span
                  className="px-2 py-0.5 rounded text-xs font-medium"
                  style={{ background: status.bg, color: status.color }}
                >
                  {status.label}
                </span>
              </div>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {bot.strategy} • {bot.mode.toUpperCase()} Mode
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg transition-colors hover:bg-[var(--bg-secondary)]"
            style={{ color: "var(--text-muted)" }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {isLoading && !detailData ? (
            <div className="flex items-center justify-center h-64">
              <Loader2
                className="animate-spin"
                size={32}
                style={{ color: "var(--accent-primary)" }}
              />
            </div>
          ) : error ? (
            <div
              className="rounded-lg border p-4 flex items-center gap-3"
              style={{
                borderColor: "var(--accent-danger)",
                background: "rgba(239, 68, 68, 0.1)",
              }}
            >
              <AlertCircle
                size={20}
                style={{ color: "var(--accent-danger)" }}
              />
              <p style={{ color: "var(--accent-danger)" }}>{error}</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Performance Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div
                  className="rounded-lg p-4"
                  style={{ background: "var(--bg-secondary)" }}
                >
                  <div
                    className="text-xs mb-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Total P&L
                  </div>
                  <div
                    className="text-xl font-bold flex items-center gap-1"
                    style={{
                      color: isProfitable
                        ? "var(--accent-success)"
                        : "var(--accent-danger)",
                    }}
                  >
                    {isProfitable ? (
                      <TrendingUp size={18} />
                    ) : (
                      <TrendingDown size={18} />
                    )}
                    {isProfitable ? "+" : ""}${totalPnl.toFixed(2)}
                  </div>
                </div>

                <div
                  className="rounded-lg p-4"
                  style={{ background: "var(--bg-secondary)" }}
                >
                  <div
                    className="text-xs mb-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Realized P&L
                  </div>
                  <div
                    className="text-xl font-bold"
                    style={{ color: "var(--text-primary)" }}
                  >
                    ${bot.realized_pnl.toFixed(2)}
                  </div>
                </div>

                <div
                  className="rounded-lg p-4"
                  style={{ background: "var(--bg-secondary)" }}
                >
                  <div
                    className="text-xs mb-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Unrealized P&L
                  </div>
                  <div
                    className="text-xl font-bold"
                    style={{ color: "var(--text-primary)" }}
                  >
                    ${bot.unrealized_pnl.toFixed(2)}
                  </div>
                </div>

                <div
                  className="rounded-lg p-4"
                  style={{ background: "var(--bg-secondary)" }}
                >
                  <div
                    className="text-xs mb-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Total Trades
                  </div>
                  <div
                    className="text-xl font-bold flex items-center gap-1"
                    style={{ color: "var(--text-primary)" }}
                  >
                    <Activity size={18} />
                    {bot.total_trades}
                  </div>
                </div>
              </div>

              {/* Risk Assessment */}
              {detailData?.risk && (
                <div
                  className="rounded-lg border p-4"
                  style={{ borderColor: "var(--border-color)" }}
                >
                  <div className="flex items-center justify-between mb-3">
                    <h3
                      className="font-medium"
                      style={{ color: "var(--text-primary)" }}
                    >
                      Risk Assessment
                    </h3>
                    <span
                      className="rounded-full px-3 py-1 text-xs font-semibold"
                      style={{
                        background: riskScoreColors[detailData.risk.score].bg,
                        color: riskScoreColors[detailData.risk.score].text,
                      }}
                    >
                      {detailData.risk.score.toUpperCase()}
                    </span>
                  </div>
                  {detailData.risk.warnings.length > 0 && (
                    <ul className="space-y-1.5">
                      {detailData.risk.warnings.map((warning, i) => (
                        <li
                          key={i}
                          className="flex items-start text-sm"
                          style={{ color: "var(--text-muted)" }}
                        >
                          <AlertCircle
                            size={14}
                            className="mr-2 mt-0.5 flex-shrink-0"
                            style={{ color: "var(--accent-warning)" }}
                          />
                          {warning}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {/* Current Positions */}
              <div
                className="rounded-lg border"
                style={{ borderColor: "var(--border-color)" }}
              >
                <button
                  onClick={() => setShowPositions(!showPositions)}
                  className="w-full px-4 py-3 flex items-center justify-between transition-colors hover:bg-[var(--bg-secondary)]"
                >
                  <h3
                    className="font-medium"
                    style={{ color: "var(--text-primary)" }}
                  >
                    Current Positions ({detailData?.positions.length || 0})
                  </h3>
                  {showPositions ? (
                    <ChevronUp
                      size={20}
                      style={{ color: "var(--text-muted)" }}
                    />
                  ) : (
                    <ChevronDown
                      size={20}
                      style={{ color: "var(--text-muted)" }}
                    />
                  )}
                </button>

                {showPositions && (
                  <div
                    className="border-t"
                    style={{ borderColor: "var(--border-color)" }}
                  >
                    {detailData?.positions.length === 0 ? (
                      <div
                        className="p-4 text-center text-sm"
                        style={{ color: "var(--text-muted)" }}
                      >
                        No open positions
                      </div>
                    ) : (
                      <div
                        className="divide-y"
                        style={{ borderColor: "var(--border-color)" }}
                      >
                        {detailData?.positions.map((position, i) => {
                          const positionPnl = position.unrealized_pnl;
                          const isProfitablePosition = positionPnl >= 0;
                          return (
                            <div key={i} className="p-4">
                              <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                  <span
                                    className="font-medium"
                                    style={{ color: "var(--text-primary)" }}
                                  >
                                    {position.symbol}
                                  </span>
                                  <span
                                    className="px-2 py-0.5 rounded text-xs font-medium"
                                    style={{
                                      background:
                                        position.side === "long"
                                          ? "rgba(34, 197, 94, 0.1)"
                                          : "rgba(239, 68, 68, 0.1)",
                                      color:
                                        position.side === "long"
                                          ? "var(--accent-success)"
                                          : "var(--accent-danger)",
                                    }}
                                  >
                                    {position.side.toUpperCase()}
                                  </span>
                                </div>
                                <span
                                  className="font-semibold"
                                  style={{
                                    color: isProfitablePosition
                                      ? "var(--accent-success)"
                                      : "var(--accent-danger)",
                                  }}
                                >
                                  {isProfitablePosition ? "+" : ""}$
                                  {positionPnl.toFixed(2)}
                                </span>
                              </div>
                              <div className="grid grid-cols-3 gap-4 text-sm">
                                <div>
                                  <span style={{ color: "var(--text-muted)" }}>
                                    Qty:{" "}
                                  </span>
                                  <span
                                    style={{ color: "var(--text-secondary)" }}
                                  >
                                    {position.qty}
                                  </span>
                                </div>
                                <div>
                                  <span style={{ color: "var(--text-muted)" }}>
                                    Entry:{" "}
                                  </span>
                                  <span
                                    style={{ color: "var(--text-secondary)" }}
                                  >
                                    ${position.entry_price.toFixed(2)}
                                  </span>
                                </div>
                                <div>
                                  <span style={{ color: "var(--text-muted)" }}>
                                    Current:{" "}
                                  </span>
                                  <span
                                    style={{ color: "var(--text-secondary)" }}
                                  >
                                    ${position.current_price.toFixed(2)}
                                  </span>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Pending Orders */}
              <div
                className="rounded-lg border"
                style={{ borderColor: "var(--border-color)" }}
              >
                <button
                  onClick={() => setShowOrders(!showOrders)}
                  className="w-full px-4 py-3 flex items-center justify-between transition-colors hover:bg-[var(--bg-secondary)]"
                >
                  <h3
                    className="font-medium"
                    style={{ color: "var(--text-primary)" }}
                  >
                    Pending Orders ({detailData?.pending_orders.length || 0})
                  </h3>
                  {showOrders ? (
                    <ChevronUp
                      size={20}
                      style={{ color: "var(--text-muted)" }}
                    />
                  ) : (
                    <ChevronDown
                      size={20}
                      style={{ color: "var(--text-muted)" }}
                    />
                  )}
                </button>

                {showOrders && (
                  <div
                    className="border-t"
                    style={{ borderColor: "var(--border-color)" }}
                  >
                    {detailData?.pending_orders.length === 0 ? (
                      <div
                        className="p-4 text-center text-sm"
                        style={{ color: "var(--text-muted)" }}
                      >
                        No pending orders
                      </div>
                    ) : (
                      <div
                        className="divide-y"
                        style={{ borderColor: "var(--border-color)" }}
                      >
                        {detailData?.pending_orders.map((order) => (
                          <div key={order.id} className="p-4">
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center gap-2">
                                <span
                                  className="font-medium"
                                  style={{ color: "var(--text-primary)" }}
                                >
                                  {order.symbol}
                                </span>
                                <span
                                  className="px-2 py-0.5 rounded text-xs font-medium"
                                  style={{
                                    background:
                                      order.side === "buy"
                                        ? "rgba(34, 197, 94, 0.1)"
                                        : "rgba(239, 68, 68, 0.1)",
                                    color:
                                      order.side === "buy"
                                        ? "var(--accent-success)"
                                        : "var(--accent-danger)",
                                  }}
                                >
                                  {order.side.toUpperCase()}
                                </span>
                              </div>
                              <span
                                className="text-xs"
                                style={{ color: "var(--text-muted)" }}
                              >
                                {order.status}
                              </span>
                            </div>
                            <div className="grid grid-cols-3 gap-4 text-sm">
                              <div>
                                <span style={{ color: "var(--text-muted)" }}>
                                  Qty:{" "}
                                </span>
                                <span
                                  style={{ color: "var(--text-secondary)" }}
                                >
                                  {order.qty}
                                </span>
                              </div>
                              <div>
                                <span style={{ color: "var(--text-muted)" }}>
                                  Type:{" "}
                                </span>
                                <span
                                  style={{ color: "var(--text-secondary)" }}
                                >
                                  {order.order_type}
                                </span>
                              </div>
                              <div>
                                <span style={{ color: "var(--text-muted)" }}>
                                  Created:{" "}
                                </span>
                                <span
                                  style={{ color: "var(--text-secondary)" }}
                                >
                                  {new Date(
                                    order.created_at,
                                  ).toLocaleTimeString()}
                                </span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Trade History */}
              <TradeHistory botId={bot.id} />
            </div>
          )}
        </div>

        {/* Actions */}
        <div
          className="px-6 py-4 border-t flex justify-between flex-shrink-0"
          style={{
            borderColor: "var(--border-color)",
            background: "var(--bg-secondary)",
          }}
        >
          <div className="flex items-center gap-2">
            {bot.status === "running" && (
              <button
                onClick={onPause}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                style={{
                  background: "rgba(234, 179, 8, 0.1)",
                  color: "var(--accent-warning)",
                }}
              >
                <Pause size={16} />
                Pause Bot
              </button>
            )}
            {bot.status === "paused" && (
              <button
                onClick={onResume}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                style={{
                  background: "rgba(34, 197, 94, 0.1)",
                  color: "var(--accent-success)",
                }}
              >
                <Play size={16} />
                Resume Bot
              </button>
            )}
            {bot.status !== "stopped" && (
              <button
                onClick={onStop}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                style={{
                  background: "rgba(239, 68, 68, 0.1)",
                  color: "var(--accent-danger)",
                }}
              >
                <Square size={16} />
                Stop Bot
              </button>
            )}
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            style={{
              border: "1px solid var(--border-color)",
              color: "var(--text-secondary)",
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
