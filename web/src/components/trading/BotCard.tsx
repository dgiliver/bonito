"use client";

import { DeployedBot } from "@/contexts/TradingContext";
import {
  Pause,
  Play,
  Square,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Activity,
} from "lucide-react";

interface BotCardProps {
  bot: DeployedBot;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onViewDetails: () => void;
}

export function BotCard({
  bot,
  onPause,
  onResume,
  onStop,
  onViewDetails,
}: BotCardProps) {
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

  return (
    <div
      className="rounded-xl border p-4 transition-all hover:shadow-md"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--border-color)",
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span
            className="w-2.5 h-2.5 rounded-full"
            style={{ background: status.color }}
          />
          <h3
            className="font-semibold text-base truncate max-w-[140px]"
            style={{ color: "var(--text-primary)" }}
            title={bot.name}
          >
            {bot.name}
          </h3>
        </div>
        <span
          className="px-2 py-0.5 rounded text-xs font-medium"
          style={{
            background:
              bot.mode === "paper"
                ? "var(--bg-tertiary)"
                : "rgba(239, 68, 68, 0.1)",
            color:
              bot.mode === "paper"
                ? "var(--text-muted)"
                : "var(--accent-danger)",
          }}
        >
          {bot.mode.toUpperCase()}
        </span>
      </div>

      {/* P&L Display */}
      <div
        className="flex items-center justify-between p-3 rounded-lg mb-3"
        style={{ background: "var(--bg-tertiary)" }}
      >
        <div className="flex items-center gap-2">
          {isProfitable ? (
            <TrendingUp size={18} style={{ color: "var(--accent-success)" }} />
          ) : (
            <TrendingDown size={18} style={{ color: "var(--accent-danger)" }} />
          )}
          <span
            className="text-lg font-bold"
            style={{
              color: isProfitable
                ? "var(--accent-success)"
                : "var(--accent-danger)",
            }}
          >
            {isProfitable ? "+" : ""}${totalPnl.toFixed(2)}
          </span>
        </div>
        <div className="text-right">
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            Realized: ${bot.realized_pnl.toFixed(2)}
          </div>
          <div className="text-xs" style={{ color: "var(--text-muted)" }}>
            Unrealized: ${bot.unrealized_pnl.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4 mb-4 text-sm">
        <div className="flex items-center gap-1.5">
          <Activity size={14} style={{ color: "var(--text-muted)" }} />
          <span style={{ color: "var(--text-secondary)" }}>
            {bot.total_trades} trades
          </span>
        </div>
        <div style={{ color: "var(--text-muted)" }}>•</div>
        <span
          className="px-1.5 py-0.5 rounded text-xs"
          style={{ background: status.bg, color: status.color }}
        >
          {status.label}
        </span>
      </div>

      {/* Strategy */}
      <div className="mb-4">
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          Strategy
        </span>
        <p
          className="text-sm font-medium truncate"
          style={{ color: "var(--text-secondary)" }}
          title={bot.strategy}
        >
          {bot.strategy}
        </p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {bot.status === "running" && (
          <button
            onClick={onPause}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
            style={{
              background: "rgba(234, 179, 8, 0.1)",
              color: "var(--accent-warning)",
            }}
          >
            <Pause size={14} />
            Pause
          </button>
        )}
        {bot.status === "paused" && (
          <button
            onClick={onResume}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
            style={{
              background: "rgba(34, 197, 94, 0.1)",
              color: "var(--accent-success)",
            }}
          >
            <Play size={14} />
            Resume
          </button>
        )}
        {bot.status !== "stopped" && (
          <button
            onClick={onStop}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
            style={{
              background: "rgba(239, 68, 68, 0.1)",
              color: "var(--accent-danger)",
            }}
          >
            <Square size={14} />
            Stop
          </button>
        )}
        <button
          onClick={onViewDetails}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium ml-auto transition-colors hover:bg-[var(--bg-tertiary)]"
          style={{
            color: "var(--text-muted)",
            border: "1px solid var(--border-color)",
          }}
        >
          Details
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}
