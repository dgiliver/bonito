"use client";

import { useState, useEffect } from "react";
import {
  TrendingUp,
  TrendingDown,
  ChevronDown,
  ChevronUp,
  Clock,
  AlertCircle,
  Loader2,
} from "lucide-react";

interface Trade {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  entry_price: number;
  exit_price: number | null;
  realized_pnl: number;
  entry_time: string;
  exit_time: string | null;
  status: "open" | "closed";
}

interface TradeHistoryProps {
  botId: string;
  maxItems?: number;
}

export function TradeHistory({ botId, maxItems = 10 }: TradeHistoryProps) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(true);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    const fetchTrades = async () => {
      try {
        setIsLoading(true);
        const response = await fetch(`/api/trading/bots/${botId}/trades`);
        if (!response.ok) throw new Error("Failed to fetch trades");
        const data = await response.json();
        setTrades(data.trades || []);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load trades");
      } finally {
        setIsLoading(false);
      }
    };

    fetchTrades();
  }, [botId]);

  const displayedTrades = showAll ? trades : trades.slice(0, maxItems);
  const hasMore = trades.length > maxItems;

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const calculateDuration = (entryTime: string, exitTime: string | null) => {
    if (!exitTime) return "Active";
    const entry = new Date(entryTime);
    const exit = new Date(exitTime);
    const durationMs = exit.getTime() - entry.getTime();
    const hours = Math.floor(durationMs / (1000 * 60 * 60));
    const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));

    if (hours > 24) {
      const days = Math.floor(hours / 24);
      return `${days}d ${hours % 24}h`;
    }
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  return (
    <div
      className="rounded-lg border"
      style={{ borderColor: "var(--border-color)" }}
    >
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between transition-colors hover:bg-[var(--bg-secondary)]"
      >
        <div className="flex items-center gap-2">
          <h3 className="font-medium" style={{ color: "var(--text-primary)" }}>
            Trade History
          </h3>
          <span className="text-sm" style={{ color: "var(--text-muted)" }}>
            ({trades.length} total)
          </span>
        </div>
        {isExpanded ? (
          <ChevronUp size={20} style={{ color: "var(--text-muted)" }} />
        ) : (
          <ChevronDown size={20} style={{ color: "var(--text-muted)" }} />
        )}
      </button>

      {isExpanded && (
        <div
          className="border-t"
          style={{ borderColor: "var(--border-color)" }}
        >
          {isLoading ? (
            <div className="p-8 flex items-center justify-center">
              <Loader2
                className="animate-spin"
                size={24}
                style={{ color: "var(--accent-primary)" }}
              />
            </div>
          ) : error ? (
            <div
              className="p-4 flex items-center gap-2"
              style={{ color: "var(--accent-danger)" }}
            >
              <AlertCircle size={16} />
              <span className="text-sm">{error}</span>
            </div>
          ) : trades.length === 0 ? (
            <div
              className="p-8 text-center text-sm"
              style={{ color: "var(--text-muted)" }}
            >
              No trades yet
            </div>
          ) : (
            <>
              <div
                className="divide-y"
                style={{ borderColor: "var(--border-color)" }}
              >
                {displayedTrades.map((trade) => {
                  const isProfitable = trade.realized_pnl >= 0;
                  const isClosed = trade.status === "closed";

                  return (
                    <div
                      key={trade.id}
                      className="p-4 hover:bg-[var(--bg-secondary)] transition-colors"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span
                            className="font-medium"
                            style={{ color: "var(--text-primary)" }}
                          >
                            {trade.symbol}
                          </span>
                          <span
                            className="px-2 py-0.5 rounded text-xs font-medium"
                            style={{
                              background:
                                trade.side === "buy"
                                  ? "rgba(34, 197, 94, 0.1)"
                                  : "rgba(239, 68, 68, 0.1)",
                              color:
                                trade.side === "buy"
                                  ? "var(--accent-success)"
                                  : "var(--accent-danger)",
                            }}
                          >
                            {trade.side.toUpperCase()}
                          </span>
                          {!isClosed && (
                            <span
                              className="px-2 py-0.5 rounded text-xs font-medium"
                              style={{
                                background: "rgba(59, 130, 246, 0.1)",
                                color: "var(--accent-primary)",
                              }}
                            >
                              OPEN
                            </span>
                          )}
                        </div>
                        {isClosed && (
                          <div className="flex items-center gap-1">
                            {isProfitable ? (
                              <TrendingUp
                                size={16}
                                style={{ color: "var(--accent-success)" }}
                              />
                            ) : (
                              <TrendingDown
                                size={16}
                                style={{ color: "var(--accent-danger)" }}
                              />
                            )}
                            <span
                              className="font-semibold"
                              style={{
                                color: isProfitable
                                  ? "var(--accent-success)"
                                  : "var(--accent-danger)",
                              }}
                            >
                              {isProfitable ? "+" : ""}$
                              {trade.realized_pnl.toFixed(2)}
                            </span>
                          </div>
                        )}
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                        <div>
                          <span style={{ color: "var(--text-muted)" }}>
                            Qty:{" "}
                          </span>
                          <span style={{ color: "var(--text-secondary)" }}>
                            {trade.qty}
                          </span>
                        </div>
                        <div>
                          <span style={{ color: "var(--text-muted)" }}>
                            Entry:{" "}
                          </span>
                          <span style={{ color: "var(--text-secondary)" }}>
                            ${trade.entry_price.toFixed(2)}
                          </span>
                        </div>
                        {trade.exit_price !== null && (
                          <div>
                            <span style={{ color: "var(--text-muted)" }}>
                              Exit:{" "}
                            </span>
                            <span style={{ color: "var(--text-secondary)" }}>
                              ${trade.exit_price.toFixed(2)}
                            </span>
                          </div>
                        )}
                        <div className="flex items-center gap-1">
                          <Clock
                            size={12}
                            style={{ color: "var(--text-muted)" }}
                          />
                          <span style={{ color: "var(--text-muted)" }}>
                            {calculateDuration(
                              trade.entry_time,
                              trade.exit_time,
                            )}
                          </span>
                        </div>
                      </div>

                      <div
                        className="mt-2 text-xs"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Entry: {formatTime(trade.entry_time)}
                        {trade.exit_time && (
                          <> • Exit: {formatTime(trade.exit_time)}</>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {hasMore && !showAll && (
                <div
                  className="p-4 border-t"
                  style={{ borderColor: "var(--border-color)" }}
                >
                  <button
                    onClick={() => setShowAll(true)}
                    className="w-full px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                    style={{
                      background: "var(--bg-secondary)",
                      color: "var(--accent-primary)",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    Show All {trades.length} Trades
                  </button>
                </div>
              )}

              {showAll && hasMore && (
                <div
                  className="p-4 border-t"
                  style={{ borderColor: "var(--border-color)" }}
                >
                  <button
                    onClick={() => setShowAll(false)}
                    className="w-full px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                    style={{
                      background: "var(--bg-secondary)",
                      color: "var(--text-secondary)",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    Show Less
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
