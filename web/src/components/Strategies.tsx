"use client";

import { useState, useEffect } from "react";
import {
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Play,
  Loader2,
  Activity,
  Calendar,
  Target,
  Award,
} from "lucide-react";
import { fetchStrategies, runBacktest } from "@/lib/api";

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
}

export default function Strategies() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [backtesting, setBacktesting] = useState(false);
  const [backtestSymbol, setBacktestSymbol] = useState("SPY");

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
    const formatted = value.toFixed(2);
    return value >= 0 ? `+${formatted}%` : `${formatted}%`;
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

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
          <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            Strategies
          </h2>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {strategies.length} saved strategies
          </p>
        </div>
        <button
          onClick={loadStrategies}
          className="btn btn-secondary"
          disabled={loading}
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Strategy List */}
        <div
          className="w-1/2 border-r overflow-y-auto p-4"
          style={{ borderColor: "var(--border-color)" }}
        >
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2
                size={32}
                className="animate-spin"
                style={{ color: "var(--text-muted)" }}
              />
            </div>
          ) : strategies.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full">
              <Activity
                size={48}
                className="mb-4"
                style={{ color: "var(--text-muted)" }}
              />
              <p style={{ color: "var(--text-muted)" }}>No strategies saved yet</p>
              <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                Create one using the AI Agent
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {strategies.map((strategy) => (
                <div
                  key={strategy.id}
                  onClick={() => setSelectedStrategy(strategy)}
                  className={`card card-hover cursor-pointer transition-all ${
                    selectedStrategy?.id === strategy.id ? "glow-border-active" : ""
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <h3
                      className="font-semibold"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {strategy.name}
                    </h3>
                    {strategy.last_backtest && (
                      <span
                        className={`badge ${
                          strategy.last_backtest.total_return >= 0
                            ? "badge-success"
                            : "badge-danger"
                        }`}
                      >
                        {strategy.last_backtest.total_return >= 0 ? (
                          <TrendingUp size={12} className="mr-1" />
                        ) : (
                          <TrendingDown size={12} className="mr-1" />
                        )}
                        {formatPercent(strategy.last_backtest.total_return)}
                      </span>
                    )}
                  </div>
                  <p
                    className="text-sm mb-3 line-clamp-2"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {strategy.description || "No description"}
                  </p>
                  <div className="flex items-center gap-3 text-xs">
                    <span style={{ color: "var(--text-muted)" }}>
                      v{strategy.version}
                    </span>
                    {strategy.tags.map((tag) => (
                      <span key={tag} className="badge">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Strategy Detail / Backtest */}
        <div className="w-1/2 overflow-y-auto p-6">
          {selectedStrategy ? (
            <div className="space-y-6">
              {/* Strategy Info */}
              <div>
                <h3
                  className="text-xl font-bold mb-2"
                  style={{ color: "var(--text-primary)" }}
                >
                  {selectedStrategy.name}
                </h3>
                <p style={{ color: "var(--text-secondary)" }}>
                  {selectedStrategy.description}
                </p>
              </div>

              {/* Run Backtest */}
              <div className="card">
                <h4
                  className="font-semibold mb-4"
                  style={{ color: "var(--text-primary)" }}
                >
                  Run Backtest
                </h4>
                <div className="flex gap-3">
                  <select
                    value={backtestSymbol}
                    onChange={(e) => setBacktestSymbol(e.target.value)}
                    className="input"
                    style={{ width: "120px" }}
                  >
                    <option value="SPY">SPY</option>
                    <option value="QQQ">QQQ</option>
                    <option value="AAPL">AAPL</option>
                  </select>
                  <button
                    onClick={() => handleBacktest(selectedStrategy.name)}
                    disabled={backtesting}
                    className="btn btn-primary flex-1"
                  >
                    {backtesting ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Play size={16} />
                    )}
                    {backtesting ? "Running..." : "Run Backtest"}
                  </button>
                </div>
              </div>

              {/* Backtest Results */}
              {backtestResult && (
                <div className="card animate-slide-up">
                  <h4
                    className="font-semibold mb-4"
                    style={{ color: "var(--text-primary)" }}
                  >
                    Results: {backtestResult.symbol}
                  </h4>

                  {/* Period */}
                  <div
                    className="flex items-center gap-2 mb-4 text-sm"
                    style={{ color: "var(--text-muted)" }}
                  >
                    <Calendar size={14} />
                    {formatDate(backtestResult.period.start)} -{" "}
                    {formatDate(backtestResult.period.end)} (
                    {backtestResult.period.bars} bars)
                  </div>

                  {/* Key Metrics */}
                  <div className="grid grid-cols-2 gap-4 mb-6">
                    <div className="card p-4">
                      <div className="flex items-center gap-2 mb-1">
                        <Target size={14} style={{ color: "var(--text-muted)" }} />
                        <span
                          className="text-xs"
                          style={{ color: "var(--text-muted)" }}
                        >
                          Total Return
                        </span>
                      </div>
                      <p
                        className="text-2xl font-bold"
                        style={{
                          color:
                            backtestResult.performance.total_return >= 0
                              ? "var(--accent-primary)"
                              : "var(--accent-danger)",
                        }}
                      >
                        {formatPercent(backtestResult.performance.total_return)}
                      </p>
                    </div>
                    <div className="card p-4">
                      <div className="flex items-center gap-2 mb-1">
                        <Activity size={14} style={{ color: "var(--text-muted)" }} />
                        <span
                          className="text-xs"
                          style={{ color: "var(--text-muted)" }}
                        >
                          Sharpe Ratio
                        </span>
                      </div>
                      <p
                        className="text-2xl font-bold"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {backtestResult.performance.sharpe_ratio.toFixed(2)}
                      </p>
                    </div>
                    <div className="card p-4">
                      <div className="flex items-center gap-2 mb-1">
                        <TrendingDown
                          size={14}
                          style={{ color: "var(--text-muted)" }}
                        />
                        <span
                          className="text-xs"
                          style={{ color: "var(--text-muted)" }}
                        >
                          Max Drawdown
                        </span>
                      </div>
                      <p
                        className="text-2xl font-bold"
                        style={{ color: "var(--accent-danger)" }}
                      >
                        -{backtestResult.performance.max_drawdown.toFixed(2)}%
                      </p>
                    </div>
                    <div className="card p-4">
                      <div className="flex items-center gap-2 mb-1">
                        <Award size={14} style={{ color: "var(--text-muted)" }} />
                        <span
                          className="text-xs"
                          style={{ color: "var(--text-muted)" }}
                        >
                          Win Rate
                        </span>
                      </div>
                      <p
                        className="text-2xl font-bold"
                        style={{ color: "var(--text-primary)" }}
                      >
                        {backtestResult.performance.win_rate.toFixed(1)}%
                      </p>
                    </div>
                  </div>

                  {/* Trade Summary */}
                  <div
                    className="border-t pt-4"
                    style={{ borderColor: "var(--border-color)" }}
                  >
                    <h5
                      className="text-sm font-medium mb-3"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      Trade Summary
                    </h5>
                    <div className="grid grid-cols-3 gap-4 text-center">
                      <div>
                        <p
                          className="text-2xl font-bold"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {backtestResult.trades.total}
                        </p>
                        <p
                          className="text-xs"
                          style={{ color: "var(--text-muted)" }}
                        >
                          Total Trades
                        </p>
                      </div>
                      <div>
                        <p
                          className="text-2xl font-bold"
                          style={{ color: "var(--accent-primary)" }}
                        >
                          {backtestResult.trades.winning}
                        </p>
                        <p
                          className="text-xs"
                          style={{ color: "var(--text-muted)" }}
                        >
                          Winning
                        </p>
                      </div>
                      <div>
                        <p
                          className="text-2xl font-bold"
                          style={{ color: "var(--accent-danger)" }}
                        >
                          {backtestResult.trades.losing}
                        </p>
                        <p
                          className="text-xs"
                          style={{ color: "var(--text-muted)" }}
                        >
                          Losing
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Capital */}
                  <div
                    className="border-t pt-4 mt-4"
                    style={{ borderColor: "var(--border-color)" }}
                  >
                    <div className="flex justify-between items-center">
                      <span style={{ color: "var(--text-muted)" }}>
                        ${backtestResult.capital.initial.toLocaleString()} →
                      </span>
                      <span
                        className="text-lg font-bold"
                        style={{ color: "var(--accent-primary)" }}
                      >
                        ${backtestResult.capital.final.toLocaleString()}
                      </span>
                    </div>
                    <p className="text-right text-sm" style={{ color: "var(--text-muted)" }}>
                      Profit: ${backtestResult.capital.profit.toLocaleString()}
                    </p>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full">
              <TrendingUp
                size={48}
                className="mb-4"
                style={{ color: "var(--text-muted)" }}
              />
              <p style={{ color: "var(--text-muted)" }}>
                Select a strategy to view details
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
