"use client";

import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

interface Trade {
  entry_time: string;
  exit_time: string;
  side: string;
  position_side?: "long" | "short";
  quantity: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  return_pct?: string;
  exit_reason?: string;
}

interface TradeLogProps {
  trades: Trade[];
  className?: string;
}

export default function TradeLog({
  trades = [],
  className = "",
}: TradeLogProps) {
  const parentRef = useRef<HTMLDivElement>(null);

  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Virtual is safe to use here
  const virtualizer = useVirtualizer({
    count: trades.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32,
    overscan: 5,
  });

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  const formatPnL = (value: number) => {
    const absValue = Math.abs(value);
    if (absValue >= 10000)
      return `${value >= 0 ? "+" : ""}$${(absValue / 1000).toFixed(0)}k`;
    if (absValue >= 1000)
      return `${value >= 0 ? "+" : ""}$${(absValue / 1000).toFixed(1)}k`;
    return `${value >= 0 ? "+" : ""}$${absValue.toFixed(0)}`;
  };

  if (trades.length === 0) {
    return (
      <div
        className="flex items-center justify-center p-4 text-sm"
        style={{ color: "var(--text-muted)" }}
        data-testid="empty-state"
      >
        No trades
      </div>
    );
  }

  return (
    <div
      className={`trade-log flex flex-col ${className}`}
      data-testid="trade-log"
    >
      <div className="flex items-center justify-between mb-2 flex-shrink-0">
        <span
          className="text-xs font-medium"
          style={{ color: "var(--text-secondary)" }}
        >
          Trade Log
        </span>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          {trades.length} trades
        </span>
      </div>

      <div
        className="rounded border overflow-hidden text-xs flex-1 flex flex-col min-h-0"
        style={{ borderColor: "var(--border-color)" }}
      >
        {/* Header */}
        <table
          className="w-full flex-shrink-0"
          style={{ background: "var(--bg-tertiary)" }}
        >
          <thead>
            <tr style={{ color: "var(--text-muted)" }}>
              <th className="text-left font-medium px-2 py-1.5 w-14">Side</th>
              <th className="text-left font-medium px-2 py-1.5 w-16">Entry</th>
              <th className="text-left font-medium px-2 py-1.5 w-16">Exit</th>
              <th className="text-right font-medium px-2 py-1.5 w-14">In</th>
              <th className="text-right font-medium px-2 py-1.5 w-14">Out</th>
              <th className="text-right font-medium px-2 py-1.5 w-20">P&L</th>
              <th className="text-right font-medium px-2 py-1.5 w-16">
                Return
              </th>
            </tr>
          </thead>
        </table>

        {/* Virtualized Rows */}
        <div
          ref={parentRef}
          data-testid="scroll-container"
          className="flex-1 overflow-y-auto min-h-0"
        >
          <div
            data-testid="virtual-container"
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              position: "relative",
            }}
            role="table"
            aria-label="Trade log"
          >
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const trade = trades[virtualRow.index];
              const isWin = trade.pnl >= 0;
              const color = isWin
                ? "var(--accent-success)"
                : "var(--accent-danger)";

              return (
                <div
                  key={virtualRow.key}
                  data-testid="trade-row"
                  className="flex items-center border-t"
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: `${virtualRow.size}px`,
                    transform: `translateY(${virtualRow.start}px)`,
                    borderColor: "var(--border-color)",
                    background:
                      virtualRow.index % 2 === 0
                        ? "var(--bg-secondary)"
                        : "transparent",
                  }}
                >
                  <div
                    className="w-14 px-2 py-1 text-left font-medium text-xs"
                    style={{
                      color:
                        trade.position_side === "short"
                          ? "var(--accent-danger)"
                          : "var(--accent-success)",
                    }}
                  >
                    {trade.position_side === "short" ? "SHORT" : "LONG"}
                  </div>
                  <div
                    className="w-16 px-2 py-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {formatDate(trade.entry_time)}
                  </div>
                  <div
                    className="w-16 px-2 py-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {formatDate(trade.exit_time)}
                  </div>
                  <div className="w-14 px-2 py-1 text-right">
                    ${trade.entry_price.toFixed(0)}
                  </div>
                  <div className="w-14 px-2 py-1 text-right">
                    ${trade.exit_price.toFixed(0)}
                  </div>
                  <div
                    className="w-20 px-2 py-1 text-right font-medium"
                    style={{ color }}
                  >
                    {formatPnL(trade.pnl)}
                  </div>
                  <div
                    className="w-16 px-2 py-1 text-right font-medium"
                    style={{ color }}
                  >
                    {trade.return_pct || "—"}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
