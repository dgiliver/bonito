"use client";

import { useState, useEffect } from "react";
import {
  TrendingUp,
  RefreshCw,
  Play,
  Loader2,
  ChevronDown,
} from "lucide-react";
import { fetchStrategies, runBacktest } from "@/lib/api";
import { EquityChart } from "./EquityChart";
import { TradeLog } from "./TradeLog";

interface Strategy {
  id: string;
  name: string;
  description: string;
  version: string;
  tags: string[];
  updated_at: string;
  last_backtest?: {
    symbol: string;
    total_return: number;
    sharpe_ratio: number;
    max_drawdown: number;
  };
}

interface EquityDataPoint {
  date: string;
  equity: number;
  drawdown: number;
  benchmark?: number;
}

interface Trade {
  entry_time: string;
  exit_time: string;
  side: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  return_pct: string;
}

interface BacktestResult {
  symbol: string;
  strategy: string;
  period: { start: string; end: string; bars: number };
  performance: {
    total_return: number;
    sharpe_ratio: number;
    max_drawdown: number;
    win_rate: number;
    profit_factor: number;
  };
  trades: { total: number; winning: number; losing: number };
  capital: { initial: number; final: number; profit: number };
  equity_curve?: EquityDataPoint[];
  trade_log?: Trade[];
}

export function Strategies() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(
    null,
  );
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(
    null,
  );
  const [backtesting, setBacktesting] = useState(false);
  const [backtestSymbol, setBacktestSymbol] = useState("SPY");
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const loadStrategies = async () => {
    setLoading(true);
    try {
      const data = await fetchStrategies();
      setStrategies(data.strategies || []);
    } catch (error) {
      console.error("Failed to load strategies:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStrategies();
  }, []);

  const handleBacktest = async (strategyName: string) => {
    setBacktesting(true);
    setBacktestResult(null);
    try {
      const result = await runBacktest({
        symbol: backtestSymbol,
        strategy_name: strategyName,
      });
      setBacktestResult(result);
    } catch (error) {
      console.error("Backtest failed:", error);
    } finally {
      setBacktesting(false);
    }
  };

  const formatPercent = (value: number) => {
    const formatted = value.toFixed(1);
    return value >= 0 ? `+${formatted}%` : `${formatted}%`;
  };

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Header Bar */}
      <header
        className="px-4 py-2 border-b flex items-center gap-3"
        style={{ borderColor: "var(--border-color)" }}
      >
        {/* Strategy Dropdown */}
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
            style={{
              background: "var(--bg-secondary)",
              color: "var(--text-primary)",
            }}
          >
            <span className="font-medium">
              {selectedStrategy?.name || "Select strategy"}
            </span>
            <ChevronDown size={14} style={{ color: "var(--text-muted)" }} />
          </button>

          {dropdownOpen && (
            <div
              className="absolute top-full left-0 mt-1 w-64 rounded-lg border shadow-lg z-50 max-h-64 overflow-y-auto"
              style={{
                background: "var(--bg-secondary)",
                borderColor: "var(--border-color)",
              }}
            >
              {loading ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2
                    size={16}
                    className="animate-spin"
                    style={{ color: "var(--text-muted)" }}
                  />
                </div>
              ) : strategies.length === 0 ? (
                <div
                  className="p-3 text-sm"
                  style={{ color: "var(--text-muted)" }}
                >
                  No strategies. Create one with the Agent.
                </div>
              ) : (
                strategies.map((strategy) => (
                  <button
                    key={strategy.id}
                    onClick={() => {
                      setSelectedStrategy(strategy);
                      setDropdownOpen(false);
                    }}
                    className="w-full px-3 py-2 text-left text-sm hover:bg-[var(--bg-tertiary)] flex items-center justify-between"
                    style={{
                      background:
                        selectedStrategy?.id === strategy.id
                          ? "var(--bg-tertiary)"
                          : "transparent",
                    }}
                  >
                    <span style={{ color: "var(--text-primary)" }}>
                      {strategy.name}
                    </span>
                    {strategy.last_backtest && (
                      <span
                        className="text-xs"
                        style={{
                          color:
                            strategy.last_backtest.total_return >= 0
                              ? "var(--accent-success)"
                              : "var(--accent-danger)",
                        }}
                      >
                        {formatPercent(strategy.last_backtest.total_return)}
                      </span>
                    )}
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Symbol Select */}
        <select
          value={backtestSymbol}
          onChange={(e) => setBacktestSymbol(e.target.value)}
          className="px-2 py-1.5 rounded-lg text-sm"
          style={{
            background: "var(--bg-secondary)",
            color: "var(--text-primary)",
            border: "none",
          }}
        >
          <option value="SPY">SPY</option>
          <option value="QQQ">QQQ</option>
          <option value="AAPL">AAPL</option>
        </select>

        {/* Run Button */}
        <button
          onClick={() =>
            selectedStrategy && handleBacktest(selectedStrategy.name)
          }
          disabled={!selectedStrategy || backtesting}
          className="btn btn-primary text-sm px-4 py-1.5"
          style={{ opacity: !selectedStrategy || backtesting ? 0.5 : 1 }}
        >
          {backtesting ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Play size={14} />
          )}
          <span className="ml-1.5">
            {backtesting ? "Running..." : "Run Backtest"}
          </span>
        </button>

        {/* Refresh */}
        <button
          onClick={loadStrategies}
          className="p-1.5 rounded hover:bg-[var(--bg-secondary)] ml-auto"
          disabled={loading}
        >
          <RefreshCw
            size={14}
            className={loading ? "animate-spin" : ""}
            style={{ color: "var(--text-muted)" }}
          />
        </button>
      </header>

      {/* Click outside to close dropdown */}
      {dropdownOpen && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setDropdownOpen(false)}
        />
      )}

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Chart Area - Takes most space */}
        <div className="flex-1 flex flex-col min-w-0">
          {backtestResult ? (
            <>
              {/* Chart */}
              {backtestResult.equity_curve &&
                backtestResult.equity_curve.length > 0 && (
                  <div
                    className="flex-1 min-h-0"
                    style={{ background: "var(--bg-secondary)" }}
                  >
                    <EquityChart
                      data={backtestResult.equity_curve}
                      initialCapital={backtestResult.capital.initial}
                      symbol={backtestResult.symbol}
                      showBenchmark={true}
                    />
                  </div>
                )}
            </>
          ) : (
            <div
              className="flex-1 flex flex-col items-center justify-center"
              style={{ color: "var(--text-muted)" }}
            >
              {selectedStrategy ? (
                <>
                  <Play size={48} className="mb-4 opacity-30" />
                  <p>Click &quot;Run Backtest&quot; to see results</p>
                </>
              ) : (
                <>
                  <TrendingUp size={48} className="mb-4 opacity-30" />
                  <p>Select a strategy to get started</p>
                </>
              )}
            </div>
          )}
        </div>

        {/* Right Panel - Metrics & Trades */}
        {backtestResult && (
          <div
            className="w-80 border-l flex flex-col overflow-y-auto"
            style={{
              borderColor: "var(--border-color)",
              background: "var(--bg-secondary)",
            }}
          >
            {/* Metrics */}
            <div
              className="p-4 border-b"
              style={{ borderColor: "var(--border-color)" }}
            >
              <h3
                className="text-sm font-medium mb-3"
                style={{ color: "var(--text-secondary)" }}
              >
                Performance
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    Return
                  </p>
                  <p
                    className="text-lg font-bold"
                    style={{
                      color:
                        backtestResult.performance.total_return >= 0
                          ? "var(--accent-success)"
                          : "var(--accent-danger)",
                    }}
                  >
                    {formatPercent(backtestResult.performance.total_return)}
                  </p>
                </div>
                <div>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    Sharpe
                  </p>
                  <p
                    className="text-lg font-bold"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {backtestResult.performance.sharpe_ratio.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    Max DD
                  </p>
                  <p
                    className="text-lg font-bold"
                    style={{ color: "var(--accent-danger)" }}
                  >
                    -{backtestResult.performance.max_drawdown.toFixed(1)}%
                  </p>
                </div>
                <div>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    Win Rate
                  </p>
                  <p
                    className="text-lg font-bold"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {backtestResult.performance.win_rate.toFixed(0)}%
                  </p>
                </div>
              </div>

              {/* Capital */}
              <div
                className="mt-3 pt-3 border-t"
                style={{ borderColor: "var(--border-color)" }}
              >
                <div className="flex justify-between text-sm">
                  <span style={{ color: "var(--text-muted)" }}>
                    ${(backtestResult.capital.initial / 1000).toFixed(0)}k →
                  </span>
                  <span
                    className="font-bold"
                    style={{ color: "var(--accent-primary)" }}
                  >
                    ${(backtestResult.capital.final / 1000).toFixed(0)}k
                  </span>
                </div>
              </div>

              {/* Trade Stats */}
              <div
                className="mt-3 pt-3 border-t flex justify-between text-sm"
                style={{ borderColor: "var(--border-color)" }}
              >
                <span style={{ color: "var(--text-muted)" }}>Trades</span>
                <span>
                  <span style={{ color: "var(--text-primary)" }}>
                    {backtestResult.trades.total}
                  </span>
                  <span style={{ color: "var(--text-muted)" }}> (</span>
                  <span style={{ color: "var(--accent-success)" }}>
                    {backtestResult.trades.winning}W
                  </span>
                  <span style={{ color: "var(--text-muted)" }}>/</span>
                  <span style={{ color: "var(--accent-danger)" }}>
                    {backtestResult.trades.losing}L
                  </span>
                  <span style={{ color: "var(--text-muted)" }}>)</span>
                </span>
              </div>
            </div>

            {/* Trade Log */}
            {backtestResult.trade_log &&
              backtestResult.trade_log.length > 0 && (
                <div className="flex-1 p-4 min-h-0 flex flex-col">
                  <TradeLog
                    trades={backtestResult.trade_log}
                    className="flex-1 min-h-0"
                  />
                </div>
              )}
          </div>
        )}
      </div>
    </div>
  );
}
