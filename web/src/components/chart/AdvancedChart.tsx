"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
} from "lightweight-charts";
import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  HistogramData,
  Time,
} from "lightweight-charts";
import {
  Search,
  ChevronDown,
  Loader2,
  Wifi,
  Database,
  AlertCircle,
} from "lucide-react";

// Types
interface OHLCVBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface OHLCVResponse {
  symbol: string;
  interval: string;
  bars: OHLCVBar[];
  source: "database" | "live";
  message?: string;
}

interface AdvancedChartProps {
  initialSymbol?: string;
  initialInterval?: string;
  initialRange?: string;
  onSymbolChange?: (symbol: string) => void;
}

const INTERVALS = [
  { value: "1m", label: "1m", intraday: true, maxDays: 7 },
  { value: "5m", label: "5m", intraday: true, maxDays: 55 },
  { value: "15m", label: "15m", intraday: true, maxDays: 55 },
  { value: "1h", label: "1h", intraday: true, maxDays: 55 },
  { value: "4h", label: "4h", intraday: true, maxDays: 55 },
  { value: "1d", label: "1D", intraday: false, maxDays: null },
];

const RANGES = ["1D", "1W", "1M", "3M", "YTD", "1Y", "5Y", "ALL"];

// Intraday intervals are limited to 60 days
const INTRADAY_RANGES = ["1D", "1W", "1M"];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AdvancedChart({
  initialSymbol = "SPY",
  initialInterval = "1d",
  initialRange = "1Y",
  onSymbolChange,
}: AdvancedChartProps) {
  // State
  const [symbol, setSymbol] = useState(initialSymbol);
  const [interval, setInterval] = useState(initialInterval);
  const [range, setRange] = useState(initialRange);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<"database" | "live">("database");
  const [dataMessage, setDataMessage] = useState<string | null>(null);
  const [symbolSearchOpen, setSymbolSearchOpen] = useState(false);
  const [intervalOpen, setIntervalOpen] = useState(false);
  const [symbols, setSymbols] = useState<{ symbol: string; name?: string }[]>(
    [],
  );
  const [searchQuery, setSearchQuery] = useState("");

  // Chart refs
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  // Check if current interval is intraday
  const isIntraday =
    INTERVALS.find((i) => i.value === interval)?.intraday ?? false;

  // Fetch OHLCV data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE}/api/chart/ohlcv?symbol=${symbol}&interval=${interval}&range=${range}`,
      );

      if (!res.ok) {
        const errorData = await res
          .json()
          .catch(() => ({ detail: "Failed to fetch data" }));
        throw new Error(errorData.detail || "Failed to fetch data");
      }

      const data: OHLCVResponse = await res.json();

      // Update data source info
      setDataSource(data.source);
      setDataMessage(data.message || null);

      if (candleSeriesRef.current && data.bars) {
        const candleData: CandlestickData<Time>[] = data.bars.map(
          (bar: OHLCVBar) => ({
            time: bar.time as Time,
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
          }),
        );
        candleSeriesRef.current.setData(candleData);
      }

      if (volumeSeriesRef.current && data.bars) {
        const volumeData: HistogramData<Time>[] = data.bars.map(
          (bar: OHLCVBar) => ({
            time: bar.time as Time,
            value: bar.volume,
            color:
              bar.close >= bar.open
                ? "rgba(34, 197, 94, 0.5)"
                : "rgba(239, 68, 68, 0.5)",
          }),
        );
        volumeSeriesRef.current.setData(volumeData);
      }

      chartRef.current?.timeScale().fitContent();
    } catch (err) {
      console.error("Failed to fetch chart data:", err);
      setError(err instanceof Error ? err.message : "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, range]);

  // Fetch symbols
  const fetchSymbols = useCallback(async () => {
    try {
      const endpoint = searchQuery
        ? `${API_BASE}/api/chart/search?q=${searchQuery}`
        : `${API_BASE}/api/chart/symbols`;
      const res = await fetch(endpoint);
      if (res.ok) {
        const data = await res.json();
        setSymbols(data.results || []);
      }
    } catch (err) {
      console.error("Failed to fetch symbols:", err);
    }
  }, [searchQuery]);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.1)" },
        horzLines: { color: "rgba(255, 255, 255, 0.1)" },
      },
      crosshair: {
        vertLine: { color: "#d4a574", labelBackgroundColor: "#2a2a2a" },
        horzLine: { color: "#d4a574", labelBackgroundColor: "#2a2a2a" },
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
        timeVisible: true,
      },
    });

    chartRef.current = chart;

    // Add candlestick series (v5 API)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    // Keep candlesticks in top 75% of chart
    candleSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.05, bottom: 0.25 },
    });
    candleSeriesRef.current = candleSeries;

    // Add volume series (v5 API) - bottom 20% of chart
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });
    volumeSeriesRef.current = volumeSeries;

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };

    window.addEventListener("resize", handleResize);
    handleResize();

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  // Fetch data when symbol/interval/range changes
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Fetch symbols when search opens or query changes
  useEffect(() => {
    if (symbolSearchOpen) {
      fetchSymbols();
    }
  }, [symbolSearchOpen, fetchSymbols]);

  // Auto-adjust range for intraday intervals
  useEffect(() => {
    if (isIntraday && !INTRADAY_RANGES.includes(range)) {
      setRange("1M"); // Max 60 days for intraday
    }
  }, [isIntraday, range]);

  // Handle symbol change
  const handleSymbolChange = (newSymbol: string) => {
    setSymbol(newSymbol);
    setSymbolSearchOpen(false);
    setSearchQuery("");
    onSymbolChange?.(newSymbol);
  };

  // Handle interval change
  const handleIntervalChange = (newInterval: string) => {
    setInterval(newInterval);
    setIntervalOpen(false);

    // Auto-adjust range for intraday
    const isNewIntraday =
      INTERVALS.find((i) => i.value === newInterval)?.intraday ?? false;
    if (isNewIntraday && !INTRADAY_RANGES.includes(range)) {
      setRange("1M");
    }
  };

  const currentIntervalLabel =
    INTERVALS.find((i) => i.value === interval)?.label || interval;

  return (
    <div
      className="advanced-chart w-full h-full flex flex-col"
      data-testid="advanced-chart"
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-3 py-2 border-b"
        style={{ borderColor: "var(--border-color)" }}
        data-testid="chart-header"
      >
        {/* Symbol Selector */}
        <div className="relative">
          <button
            onClick={() => setSymbolSearchOpen(!symbolSearchOpen)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg font-semibold"
            style={{
              background: "var(--bg-secondary)",
              color: "var(--text-primary)",
            }}
            data-testid="symbol-selector"
          >
            <span>{symbol}</span>
            <ChevronDown size={14} />
          </button>

          {symbolSearchOpen && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setSymbolSearchOpen(false)}
              />
              <div
                className="absolute top-full left-0 mt-1 w-64 rounded-lg border shadow-lg z-50"
                style={{
                  background: "var(--bg-secondary)",
                  borderColor: "var(--border-color)",
                }}
                data-testid="symbol-search"
              >
                <div
                  className="p-2 border-b"
                  style={{ borderColor: "var(--border-color)" }}
                >
                  <div
                    className="flex items-center gap-2 px-2 py-1 rounded"
                    style={{ background: "var(--bg-tertiary)" }}
                  >
                    <Search size={14} style={{ color: "var(--text-muted)" }} />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search symbols..."
                      className="flex-1 bg-transparent border-none outline-none text-sm"
                      style={{ color: "var(--text-primary)" }}
                      autoFocus
                    />
                  </div>
                </div>
                <div className="max-h-48 overflow-y-auto">
                  {symbols.map((s) => (
                    <button
                      key={s.symbol}
                      onClick={() => handleSymbolChange(s.symbol)}
                      className="w-full px-3 py-2 text-left text-sm hover:bg-[var(--bg-tertiary)] flex justify-between"
                    >
                      <span style={{ color: "var(--text-primary)" }}>
                        {s.symbol}
                      </span>
                      {s.name && (
                        <span
                          className="text-xs truncate ml-2"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {s.name}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Interval Selector */}
        <div className="relative">
          <button
            onClick={() => setIntervalOpen(!intervalOpen)}
            className="flex items-center gap-1 px-2 py-1.5 rounded text-sm"
            style={{
              background: "var(--bg-secondary)",
              color: "var(--text-secondary)",
            }}
            data-testid="interval-selector"
          >
            <span>{currentIntervalLabel}</span>
            <ChevronDown size={12} />
          </button>

          {intervalOpen && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setIntervalOpen(false)}
              />
              <div
                className="absolute top-full left-0 mt-1 rounded-lg border shadow-lg z-50 py-1"
                style={{
                  background: "var(--bg-secondary)",
                  borderColor: "var(--border-color)",
                }}
              >
                {INTERVALS.map((i) => (
                  <button
                    key={i.value}
                    onClick={() => handleIntervalChange(i.value)}
                    className="w-full px-4 py-1.5 text-left text-sm hover:bg-[var(--bg-tertiary)] flex items-center justify-between"
                    style={{
                      color:
                        interval === i.value
                          ? "var(--accent-primary)"
                          : "var(--text-secondary)",
                    }}
                  >
                    <span>{i.label}</span>
                    {i.intraday && i.maxDays && (
                      <span
                        className="text-xs px-1 rounded"
                        style={{
                          background: "var(--bg-tertiary)",
                          color: "var(--text-muted)",
                        }}
                      >
                        {i.maxDays}d
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Data Source Badge */}
        {!loading && !error && (
          <div
            className="flex items-center gap-1 px-2 py-1 rounded text-xs"
            style={{
              background:
                dataSource === "live"
                  ? "rgba(59, 130, 246, 0.2)"
                  : "var(--bg-tertiary)",
              color: dataSource === "live" ? "#3b82f6" : "var(--text-muted)",
            }}
            title={
              dataMessage ||
              (dataSource === "live"
                ? "Live from Yahoo Finance"
                : "From database")
            }
          >
            {dataSource === "live" ? (
              <Wifi size={12} />
            ) : (
              <Database size={12} />
            )}
            <span>{dataSource === "live" ? "LIVE" : "DB"}</span>
          </div>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Range Selector */}
        <div className="flex items-center gap-1" data-testid="range-selector">
          {RANGES.map((r) => {
            const disabled = isIntraday && !INTRADAY_RANGES.includes(r);
            return (
              <button
                key={r}
                onClick={() => !disabled && setRange(r)}
                className={`px-2 py-1 text-xs rounded transition-colors ${range === r ? "active" : ""}`}
                style={{
                  background:
                    range === r ? "var(--accent-primary)" : "transparent",
                  color:
                    range === r
                      ? "var(--bg-primary)"
                      : disabled
                        ? "var(--text-muted)"
                        : "var(--text-muted)",
                  opacity: disabled ? 0.4 : 1,
                  cursor: disabled ? "not-allowed" : "pointer",
                }}
                disabled={disabled}
                title={
                  disabled ? "Intraday data limited to 60 days" : undefined
                }
                data-testid={`range-${r}`}
              >
                {r}
              </button>
            );
          })}
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="flex-1 relative" data-testid="chart-canvas">
        {loading && (
          <div
            className="absolute inset-0 flex items-center justify-center z-10"
            style={{ background: "var(--bg-primary)" }}
            data-testid="chart-loading"
          >
            <Loader2
              className="animate-spin"
              size={32}
              style={{ color: "var(--text-muted)" }}
            />
          </div>
        )}

        {error && !loading && (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center z-10 gap-2"
            style={{ background: "var(--bg-primary)" }}
          >
            <AlertCircle size={32} style={{ color: "var(--accent-danger)" }} />
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {error}
            </p>
          </div>
        )}

        <div ref={chartContainerRef} className="w-full h-full" />
      </div>

      {/* Footer message for live data */}
      {dataMessage && !loading && !error && (
        <div
          className="px-3 py-1 text-xs border-t"
          style={{
            borderColor: "var(--border-color)",
            color: "var(--text-muted)",
          }}
        >
          {dataMessage}
        </div>
      )}
    </div>
  );
}
