"use client";

import { useState, useEffect } from "react";
import {
  Database,
  RefreshCw,
  Download,
  Loader2,
  Calendar,
  BarChart3,
} from "lucide-react";
import { fetchSymbols, ingestData } from "@/lib/api";

interface SymbolData {
  symbol: string;
  start: string;
  end: string;
  bars: number;
}

export function Data() {
  const [symbols, setSymbols] = useState<SymbolData[]>([]);
  const [loading, setLoading] = useState(true);
  const [ingesting, setIngesting] = useState(false);

  // Ingest form
  const [newSymbol, setNewSymbol] = useState("");
  const [startDate, setStartDate] = useState("2020-01-01");
  const [timeframe, setTimeframe] = useState("1d");

  const loadSymbols = async () => {
    setLoading(true);
    try {
      const data = await fetchSymbols();
      setSymbols(data.symbols || []);
    } catch (error) {
      console.error("Failed to load symbols:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSymbols();
  }, []);

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSymbol.trim()) return;

    setIngesting(true);
    try {
      await ingestData({
        symbols: [newSymbol.toUpperCase()],
        start: startDate,
        timeframe,
      });
      setNewSymbol("");
      await loadSymbols();
    } catch (error) {
      console.error("Failed to ingest data:", error);
    } finally {
      setIngesting(false);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  const totalBars = symbols.reduce((sum, s) => sum + s.bars, 0);

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
            Market Data
          </h2>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {symbols.length} symbols • {totalBars.toLocaleString()} bars
          </p>
        </div>
        <button
          onClick={loadSymbols}
          className="btn btn-secondary"
          disabled={loading}
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Data List */}
        <div
          className="flex-1 border-r overflow-y-auto p-4"
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
          ) : symbols.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full">
              <Database
                size={48}
                className="mb-4"
                style={{ color: "var(--text-muted)" }}
              />
              <p style={{ color: "var(--text-muted)" }}>No data ingested yet</p>
              <p
                className="text-sm mt-1"
                style={{ color: "var(--text-muted)" }}
              >
                Use the form to download market data
              </p>
            </div>
          ) : (
            <div className="grid gap-3">
              {symbols.map((symbol) => (
                <div key={symbol.symbol} className="card card-hover">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-10 h-10 rounded-lg flex items-center justify-center font-bold"
                        style={{
                          background: "var(--bg-tertiary)",
                          color: "var(--accent-primary)",
                        }}
                      >
                        {symbol.symbol.slice(0, 2)}
                      </div>
                      <div>
                        <h3
                          className="font-semibold"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {symbol.symbol}
                        </h3>
                        <div
                          className="flex items-center gap-2 text-xs"
                          style={{ color: "var(--text-muted)" }}
                        >
                          <Calendar size={12} />
                          {formatDate(symbol.start)} - {formatDate(symbol.end)}
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="flex items-center gap-1">
                        <BarChart3
                          size={14}
                          style={{ color: "var(--text-muted)" }}
                        />
                        <span
                          className="font-semibold"
                          style={{ color: "var(--text-primary)" }}
                        >
                          {symbol.bars.toLocaleString()}
                        </span>
                      </div>
                      <span
                        className="text-xs"
                        style={{ color: "var(--text-muted)" }}
                      >
                        bars
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Ingest Form */}
        <div className="w-80 p-6 overflow-y-auto">
          <h3
            className="font-semibold mb-4"
            style={{ color: "var(--text-primary)" }}
          >
            Download Data
          </h3>
          <form onSubmit={handleIngest} className="space-y-4">
            <div>
              <label
                className="block text-sm mb-2"
                style={{ color: "var(--text-secondary)" }}
              >
                Symbol
              </label>
              <input
                type="text"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                placeholder="AAPL, MSFT, etc."
                className="input"
              />
            </div>

            <div>
              <label
                className="block text-sm mb-2"
                style={{ color: "var(--text-secondary)" }}
              >
                Start Date
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="input"
              />
            </div>

            <div>
              <label
                className="block text-sm mb-2"
                style={{ color: "var(--text-secondary)" }}
              >
                Timeframe
              </label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="input"
              >
                <option value="1d">Daily (1d)</option>
                <option value="1h">Hourly (1h)</option>
                <option value="5m">5 Minute</option>
                <option value="1m">1 Minute</option>
              </select>
              <p
                className="text-xs mt-1"
                style={{ color: "var(--text-muted)" }}
              >
                Note: Intraday data limited to 60 days (Yahoo)
              </p>
            </div>

            <button
              type="submit"
              disabled={!newSymbol.trim() || ingesting}
              className="btn btn-primary w-full"
            >
              {ingesting ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Download size={16} />
              )}
              {ingesting ? "Downloading..." : "Download Data"}
            </button>
          </form>

          {/* Quick Add */}
          <div className="mt-6">
            <h4
              className="text-sm font-medium mb-3"
              style={{ color: "var(--text-secondary)" }}
            >
              Popular Symbols
            </h4>
            <div className="flex flex-wrap gap-2">
              {[
                "AAPL",
                "MSFT",
                "GOOGL",
                "AMZN",
                "NVDA",
                "TSLA",
                "META",
                "BTC-USD",
              ].map((sym) => (
                <button
                  key={sym}
                  onClick={() => setNewSymbol(sym)}
                  className="btn btn-ghost px-3 py-1.5 text-xs"
                  style={{
                    background: symbols.some((s) => s.symbol === sym)
                      ? "var(--bg-tertiary)"
                      : "transparent",
                    color: symbols.some((s) => s.symbol === sym)
                      ? "var(--accent-primary)"
                      : "var(--text-secondary)",
                  }}
                >
                  {sym}
                </button>
              ))}
            </div>
          </div>

          {/* Storage Info */}
          <div className="mt-6 card p-4">
            <h4
              className="text-sm font-medium mb-2"
              style={{ color: "var(--text-secondary)" }}
            >
              Storage
            </h4>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span style={{ color: "var(--text-muted)" }}>Database</span>
                <span style={{ color: "var(--text-primary)" }}>DuckDB</span>
              </div>
              <div className="flex justify-between">
                <span style={{ color: "var(--text-muted)" }}>Location</span>
                <span style={{ color: "var(--text-primary)" }}>Local</span>
              </div>
              <div className="flex justify-between">
                <span style={{ color: "var(--text-muted)" }}>Data Source</span>
                <span style={{ color: "var(--text-primary)" }}>
                  Yahoo Finance
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
