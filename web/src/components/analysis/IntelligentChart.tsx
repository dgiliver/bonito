"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
} from "lightweight-charts";
import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  HistogramData,
  Time,
  SeriesMarker,
  ISeriesMarkersPluginApi,
} from "lightweight-charts";
import {
  Search,
  ChevronDown,
  Loader2,
  Wifi,
  Database,
  AlertCircle,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import {
  useAnalysis,
  useChartIntents,
  Trade,
  ChartEvent as AnalysisChartEvent,
} from "@/contexts/AnalysisContext";

// ============================================================================
// Types
// ============================================================================

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

// ============================================================================
// Constants
// ============================================================================

const INTERVALS = [
  { value: "1m", label: "1m", intraday: true, maxDays: 7 },
  { value: "5m", label: "5m", intraday: true, maxDays: 55 },
  { value: "15m", label: "15m", intraday: true, maxDays: 55 },
  { value: "1h", label: "1h", intraday: true, maxDays: 55 },
  { value: "4h", label: "4h", intraday: true, maxDays: 55 },
  { value: "1d", label: "1D", intraday: false, maxDays: null },
];

const RANGES = ["1D", "1W", "1M", "3M", "YTD", "1Y", "5Y", "ALL"];
const INTRADAY_RANGES = ["1D", "1W", "1M"];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ============================================================================
// Trade Markers
// ============================================================================

function createTradeMarkers(
  trades: Trade[],
  candleData: CandlestickData<Time>[],
  selectedTradeId?: string | null,
): SeriesMarker<Time>[] {
  const markers: SeriesMarker<Time>[] = [];

  if (!candleData.length || !trades.length) return markers;

  // Get candle timestamps - normalize to start of day for daily charts
  const candleTimes = candleData.map((c) => c.time as number);
  const minTime = Math.min(...candleTimes);
  const maxTime = Math.max(...candleTimes);

  // Helper to find nearest candle time
  const findNearestCandleTime = (timestamp: number): Time | null => {
    // For daily charts, normalize to start of day
    const dayTimestamp = Math.floor(timestamp / 86400) * 86400;

    // Check if this day exists in our candle data
    if (candleTimes.includes(dayTimestamp)) {
      return dayTimestamp as Time;
    }

    // Find closest candle within range
    if (timestamp < minTime || timestamp > maxTime) return null;

    // Find the nearest candle time
    let closest = candleTimes[0];
    let minDiff = Math.abs(candleTimes[0] - timestamp);
    for (const t of candleTimes) {
      const diff = Math.abs(t - timestamp);
      if (diff < minDiff) {
        minDiff = diff;
        closest = t;
      }
    }
    // Only use if within 1 day
    return minDiff <= 86400 ? (closest as Time) : null;
  };

  for (const trade of trades) {
    const isSelected = trade.id === selectedTradeId;
    const entryTs = Math.floor(new Date(trade.entry_time).getTime() / 1000);
    const exitTs = Math.floor(new Date(trade.exit_time).getTime() / 1000);

    const entryTime = findNearestCandleTime(entryTs);
    const exitTime = findNearestCandleTime(exitTs);

    // Entry marker - highlighted if selected
    if (entryTime !== null) {
      markers.push({
        time: entryTime,
        position: "belowBar",
        color: isSelected
          ? "#fbbf24"
          : trade.side === "long"
            ? "#22c55e"
            : "#ef4444",
        shape: isSelected ? "circle" : "arrowUp",
        size: isSelected ? 3 : 1,
        text: isSelected
          ? `★ ENTRY $${trade.entry_price.toFixed(2)}`
          : `Entry $${trade.entry_price.toFixed(2)}`,
        id: `entry-${trade.id}`,
      });
    }

    // Exit marker - highlighted if selected
    if (exitTime !== null) {
      markers.push({
        time: exitTime,
        position: "aboveBar",
        color: isSelected ? "#fbbf24" : trade.pnl >= 0 ? "#22c55e" : "#ef4444",
        shape: isSelected ? "circle" : "arrowDown",
        size: isSelected ? 3 : 1,
        text: isSelected
          ? `★ EXIT ${trade.pnl >= 0 ? "+" : ""}$${trade.pnl.toFixed(0)}`
          : `Exit ${trade.pnl >= 0 ? "+" : ""}$${trade.pnl.toFixed(0)}`,
        id: `exit-${trade.id}`,
      });
    }
  }

  // Sort markers by time
  return markers.sort((a, b) => (a.time as number) - (b.time as number));
}

// ============================================================================
// Main Component
// ============================================================================

export default function IntelligentChart() {
  const { state, dispatch, emitChartEvent } = useAnalysis();
  const { intents, processIntent } = useChartIntents();

  // Local state
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
  const [range, setRange] = useState("1Y");
  const [candleData, setCandleData] = useState<CandlestickData<Time>[]>([]);
  const [pendingZoom, setPendingZoom] = useState<{
    start: number;
    end: number;
  } | null>(null);
  // Ref to track pendingZoom for use in fetchData (avoids stale closure)
  const pendingZoomRef = useRef<{ start: number; end: number } | null>(null);
  const lastBacktestId = useRef<string | null>(null);

  // Keep ref in sync with state
  useEffect(() => {
    pendingZoomRef.current = pendingZoom;
  }, [pendingZoom]);

  // Chart refs
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Derived values
  const { symbol, interval } = state.chart;
  const isIntraday =
    INTERVALS.find((i) => i.value === interval)?.intraday ?? false;
  const trades = useMemo(
    () => state.backtest.result?.trades || [],
    [state.backtest.result?.trades],
  );

  // ============================================================================
  // Data Fetching
  // ============================================================================

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

      setDataSource(data.source);
      setDataMessage(data.message || null);

      if (candleSeriesRef.current && data.bars) {
        const candles: CandlestickData<Time>[] = data.bars.map(
          (bar: OHLCVBar) => ({
            time: bar.time as Time,
            open: bar.open,
            high: bar.high,
            low: bar.low,
            close: bar.close,
          }),
        );
        candleSeriesRef.current.setData(candles);
        setCandleData(candles);
        console.log("[Chart] Loaded candles:", {
          count: candles.length,
          firstTime: candles[0]?.time,
          firstDate: candles[0]?.time
            ? new Date((candles[0].time as number) * 1000).toISOString()
            : null,
          lastTime: candles[candles.length - 1]?.time,
          lastDate: candles[candles.length - 1]?.time
            ? new Date(
                (candles[candles.length - 1].time as number) * 1000,
              ).toISOString()
            : null,
        });
        // Trade markers are updated in a separate effect when trades change
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

      // Only fit content if no pending zoom (backtest will apply its own zoom)
      // Use ref to get current value (avoids stale closure)
      if (!pendingZoomRef.current) {
        chartRef.current?.timeScale().fitContent();
      } else {
        console.log("[Chart] Skipping fitContent - pending zoom exists");
      }
    } catch (err) {
      console.error("Failed to fetch chart data:", err);
      setError(err instanceof Error ? err.message : "Failed to fetch data");
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, range]);

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

  // ============================================================================
  // Chart Initialization
  // ============================================================================

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.05)" },
        horzLines: { color: "rgba(255, 255, 255, 0.05)" },
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

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    candleSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.05, bottom: 0.25 },
    });
    candleSeriesRef.current = candleSeries;

    // Create markers plugin for trade visualization
    const markersPlugin = createSeriesMarkers(candleSeries, []);
    markersPluginRef.current = markersPlugin;

    // Volume series
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });
    volumeSeriesRef.current = volumeSeries;

    // Handle click events
    chart.subscribeClick((param) => {
      if (!param.time) return;

      const event: AnalysisChartEvent = {
        type: "click",
        timestamp: param.time as number,
        price: param.point
          ? candleSeries.coordinateToPrice(param.point.y) || undefined
          : undefined,
      };

      // Check if clicked on a marker (trade)
      // Note: Lightweight Charts doesn't expose marker clicks directly,
      // so we approximate by checking if click is near a trade
      const clickTime = param.time as number;
      const nearbyTrade = trades.find((t) => {
        const entryTime = Math.floor(new Date(t.entry_time).getTime() / 1000);
        const exitTime = Math.floor(new Date(t.exit_time).getTime() / 1000);
        return (
          Math.abs(clickTime - entryTime) < 86400 ||
          Math.abs(clickTime - exitTime) < 86400
        );
      });

      if (nearbyTrade) {
        event.target = { type: "trade", tradeId: nearbyTrade.id };
      }

      emitChartEvent(event);
    });

    // Handle visible range change
    chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
      if (range) {
        emitChartEvent({
          type: "range_change",
          visibleRange: {
            start: range.from as number,
            end: range.to as number,
          },
        });
      }
    });

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };

    // Use ResizeObserver to detect container size changes (e.g., panel collapse)
    const resizeObserver = new ResizeObserver(handleResize);
    if (chartContainerRef.current) {
      resizeObserver.observe(chartContainerRef.current);
    }

    window.addEventListener("resize", handleResize);
    handleResize();

    return () => {
      window.removeEventListener("resize", handleResize);
      resizeObserver.disconnect();
      // Clean up markers plugin
      if (markersPluginRef.current) {
        markersPluginRef.current.detach();
        markersPluginRef.current = null;
      }
      chart.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Chart init runs once; click handlers use current trades via closure
  }, []);

  // ============================================================================
  // Data Effects
  // ============================================================================

  // Fetch data when symbol/interval/range changes
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Get selected trade from state
  const selectedTrade = state.backtest.selectedTrade;

  // Update trade markers when trades or selection changes
  useEffect(() => {
    if (markersPluginRef.current) {
      if (candleData.length > 0 && trades.length > 0) {
        const markers = createTradeMarkers(
          trades,
          candleData,
          selectedTrade?.id,
        );
        console.log(
          `[Chart] Creating ${markers.length} markers for ${trades.length} trades${selectedTrade ? ` (selected: ${selectedTrade.id})` : ""}`,
        );
        markersPluginRef.current.setMarkers(markers);
      } else {
        markersPluginRef.current.setMarkers([]);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Only re-run when ID changes, not full object
  }, [trades, candleData, selectedTrade?.id]);

  // Zoom to selected trade when viewing trade details
  useEffect(() => {
    if (!selectedTrade || !chartRef.current || candleData.length === 0) return;

    const entryTs = Math.floor(
      new Date(selectedTrade.entry_time).getTime() / 1000,
    );
    const exitTs = Math.floor(
      new Date(selectedTrade.exit_time).getTime() / 1000,
    );

    // Add padding: show 20% extra time on each side for context
    const tradeDuration = exitTs - entryTs;
    const padding = Math.max(tradeDuration * 0.3, 86400 * 7); // At least 7 days padding

    const zoomStart = entryTs - padding;
    const zoomEnd = exitTs + padding;

    console.log(
      `[Chart] Zooming to selected trade: ${new Date(entryTs * 1000).toLocaleDateString()} - ${new Date(exitTs * 1000).toLocaleDateString()}`,
    );

    requestAnimationFrame(() => {
      if (chartRef.current) {
        chartRef.current.timeScale().setVisibleRange({
          from: zoomStart as Time,
          to: zoomEnd as Time,
        });
      }
    });
  }, [selectedTrade, candleData]);

  // Fetch symbols when search opens
  useEffect(() => {
    if (symbolSearchOpen) {
      fetchSymbols();
    }
  }, [symbolSearchOpen, fetchSymbols]);

  // Auto-adjust range for intraday
  useEffect(() => {
    if (isIntraday && !INTRADAY_RANGES.includes(range)) {
      setRange("1M");
    }
  }, [isIntraday, range]);

  // Smart symbol + range selection when backtest completes
  useEffect(() => {
    const backtestResult = state.backtest.result;
    if (!backtestResult?.period?.start || !backtestResult?.period?.end) return;

    // Create a unique ID for this backtest
    const backtestId = `${backtestResult.strategy_name}_${backtestResult.symbol}_${backtestResult.period.start}_${backtestResult.period.end}`;
    if (lastBacktestId.current === backtestId) return; // Already processed
    lastBacktestId.current = backtestId;

    // Sync chart symbol to backtest symbol
    if (backtestResult.symbol && backtestResult.symbol !== symbol) {
      console.log(
        `[Chart] Switching symbol from ${symbol} to ${backtestResult.symbol} for backtest`,
      );
      dispatch({ type: "SET_SYMBOL", symbol: backtestResult.symbol });
    }

    const startDate = new Date(backtestResult.period.start);
    const endDate = new Date(backtestResult.period.end);
    const now = new Date();

    console.log("[Chart] ========== BACKTEST ZOOM DEBUG ==========");
    console.log("[Chart] Raw period:", backtestResult.period);
    console.log("[Chart] Parsed startDate:", startDate.toISOString());
    console.log("[Chart] Parsed endDate:", endDate.toISOString());

    // Calculate backtest duration and how far back it starts
    const backtestDays = Math.ceil(
      (endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24),
    );
    const daysBack = Math.ceil(
      (now.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24),
    );

    // Select range that covers the backtest period
    // Be aggressive about using ALL for anything more than 3 years back
    let newRange: string;
    if (daysBack > 365 * 3 || backtestDays > 365 * 3) {
      newRange = "ALL";
    } else if (daysBack > 365 * 1.5 || backtestDays > 365 * 1.5) {
      newRange = "5Y";
    } else if (daysBack > 365 || backtestDays > 365) {
      newRange = "1Y";
    } else if (daysBack > 200 || backtestDays > 200) {
      newRange = "YTD";
    } else if (daysBack > 60 || backtestDays > 60) {
      newRange = "3M";
    } else if (daysBack > 14 || backtestDays > 14) {
      newRange = "1M";
    } else {
      newRange = "1W";
    }

    console.log(
      `[Chart] Backtest: ${backtestDays} days duration, ${daysBack} days back → range=${newRange}`,
    );

    // Calculate zoom range with padding
    const startTs = Math.floor(startDate.getTime() / 1000);
    const endTs = Math.floor(endDate.getTime() / 1000);
    const padding = (endTs - startTs) * 0.05;
    const zoomRange = { start: startTs - padding, end: endTs + padding };

    console.log(
      `[Chart] Zoom target: ${new Date(zoomRange.start * 1000).toLocaleDateString()} - ${new Date(zoomRange.end * 1000).toLocaleDateString()}`,
    );

    // Update range if needed - this will trigger a data fetch
    if (newRange !== range && !isIntraday) {
      console.log(`[Chart] Changing range from ${range} to ${newRange}`);
      // Set pending zoom AFTER setting range to avoid race condition
      // The fetch will use the ref, and the effect will run after new data loads
      setRange(newRange);
      // Use setTimeout to ensure state update propagates before setting pendingZoom
      setTimeout(() => {
        setPendingZoom(zoomRange);
      }, 0);
      return; // Exit early - zoom will be applied after new data loads
    }

    // Range already correct - set pending zoom and try to apply immediately
    setPendingZoom(zoomRange);

    if (candleData.length > 0 && chartRef.current) {
      // Range is already correct and we have data - apply zoom now
      const dataStart = candleData[0]?.time as number;
      const dataEnd = candleData[candleData.length - 1]?.time as number;
      const zStart = Math.max(dataStart, zoomRange.start);
      const zEnd = Math.min(dataEnd, zoomRange.end);

      console.log(
        `[Chart] Data range: ${new Date(dataStart * 1000).toLocaleDateString()} - ${new Date(dataEnd * 1000).toLocaleDateString()}`,
      );
      console.log(
        `[Chart] Calculated zoom: ${new Date(zStart * 1000).toLocaleDateString()} - ${new Date(zEnd * 1000).toLocaleDateString()}`,
      );

      if (zStart < zEnd) {
        console.log("[Chart] Applying setVisibleRange with:", {
          from: zStart,
          to: zEnd,
          fromDate: new Date(zStart * 1000).toISOString(),
          toDate: new Date(zEnd * 1000).toISOString(),
        });
        requestAnimationFrame(() => {
          if (chartRef.current) {
            chartRef.current.timeScale().setVisibleRange({
              from: zStart as Time,
              to: zEnd as Time,
            });
            console.log("[Chart] Immediate zoom applied successfully");
          }
        });
      }
      // Clear pending zoom since we applied it
      setPendingZoom(null);
    }
    // If no data yet, pendingZoom will be applied when data loads
    console.log("[Chart] ========== END DEBUG ==========");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Only react to backtest result changes
  }, [state.backtest.result]);

  // Apply pending zoom after data loads
  useEffect(() => {
    if (
      !pendingZoom ||
      candleData.length === 0 ||
      !chartRef.current ||
      loading
    ) {
      return;
    }

    const dataStart = candleData[0]?.time as number;
    const dataEnd = candleData[candleData.length - 1]?.time as number;

    console.log("[Chart] Raw timestamps:", {
      dataStart,
      dataEnd,
      pendingStart: pendingZoom.start,
      pendingEnd: pendingZoom.end,
      candleCount: candleData.length,
      firstCandle: candleData[0],
      lastCandle: candleData[candleData.length - 1],
    });
    console.log(
      `[Chart] Pending zoom check: data=${new Date(dataStart * 1000).toLocaleDateString()}-${new Date(dataEnd * 1000).toLocaleDateString()}, ` +
        `target=${new Date(pendingZoom.start * 1000).toLocaleDateString()}-${new Date(pendingZoom.end * 1000).toLocaleDateString()}`,
    );

    // Calculate intersection
    const zoomStart = Math.max(dataStart, pendingZoom.start);
    const zoomEnd = Math.min(dataEnd, pendingZoom.end);

    if (zoomStart < zoomEnd) {
      // Use requestAnimationFrame for more reliable timing
      requestAnimationFrame(() => {
        if (chartRef.current) {
          console.log(
            `[Chart] Applying zoom: ${new Date(zoomStart * 1000).toLocaleDateString()} - ${new Date(zoomEnd * 1000).toLocaleDateString()}`,
          );
          chartRef.current.timeScale().setVisibleRange({
            from: zoomStart as Time,
            to: zoomEnd as Time,
          });
        }
      });
      // Only clear pendingZoom after successful zoom
      setPendingZoom(null);
    } else {
      // Data doesn't cover backtest period - might be stale, wait for fresh data
      console.log(
        `[Chart] No overlap yet - data may be stale, waiting for fresh data...`,
      );
      // Don't clear pendingZoom - let it retry when new data arrives
    }
  }, [pendingZoom, candleData, loading]);

  // ============================================================================
  // Process Agent Intents
  // ============================================================================

  useEffect(() => {
    for (const intent of intents) {
      if (intent.processed) continue;

      switch (intent.type) {
        case "navigate":
          if (intent.timestamp && chartRef.current) {
            chartRef.current
              .timeScale()
              .scrollToPosition(intent.timestamp, false);
          }
          if (intent.range && chartRef.current) {
            chartRef.current.timeScale().setVisibleRange({
              from: intent.range.start as Time,
              to: intent.range.end as Time,
            });
          }
          break;

        case "overlay":
          if (intent.indicator) {
            dispatch({ type: "ADD_INDICATOR", indicator: intent.indicator });
          }
          break;

        case "clear":
          if (
            intent.clearType === "annotations" ||
            intent.clearType === "all"
          ) {
            dispatch({ type: "CLEAR_ANNOTATIONS" });
          }
          break;
      }

      processIntent(intent.id);
    }
  }, [intents, dispatch, processIntent]);

  // ============================================================================
  // Handlers
  // ============================================================================

  const handleSymbolChange = (newSymbol: string) => {
    dispatch({ type: "SET_SYMBOL", symbol: newSymbol });
    setSymbolSearchOpen(false);
    setSearchQuery("");
  };

  const handleIntervalChange = (newInterval: string) => {
    dispatch({ type: "SET_INTERVAL", interval: newInterval });
    setIntervalOpen(false);

    const isNewIntraday =
      INTERVALS.find((i) => i.value === newInterval)?.intraday ?? false;
    if (isNewIntraday && !INTRADAY_RANGES.includes(range)) {
      setRange("1M");
    }
  };

  const currentIntervalLabel =
    INTERVALS.find((i) => i.value === interval)?.label || interval;

  // ============================================================================
  // Render
  // ============================================================================

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex items-center gap-2 px-3 py-2 border-b"
        style={{ borderColor: "var(--border-color)" }}
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

        {/* Trade Stats Badge */}
        {trades.length > 0 && (
          <div
            className="flex items-center gap-1.5 px-2 py-1 rounded text-xs"
            style={{ background: "var(--bg-tertiary)" }}
          >
            <span style={{ color: "var(--text-muted)" }}>
              {trades.length} trades
            </span>
            <span style={{ color: "var(--text-muted)" }}>|</span>
            <span style={{ color: "var(--accent-success)" }}>
              <TrendingUp size={10} className="inline mr-0.5" />
              {trades.filter((t) => t.pnl > 0).length}
            </span>
            <span style={{ color: "var(--accent-danger)" }}>
              <TrendingDown size={10} className="inline mr-0.5" />
              {trades.filter((t) => t.pnl <= 0).length}
            </span>
          </div>
        )}

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
        <div className="flex items-center gap-1">
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
              >
                {r}
              </button>
            );
          })}
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="flex-1 relative">
        {loading && (
          <div
            className="absolute inset-0 flex items-center justify-center z-10"
            style={{ background: "var(--bg-primary)" }}
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

      {/* Footer with selected trade info */}
      {state.backtest.selectedTrade && (
        <div
          className="px-3 py-2 border-t flex items-center gap-4 text-sm"
          style={{
            borderColor: "var(--border-color)",
            background: "var(--bg-secondary)",
          }}
        >
          <span style={{ color: "var(--text-muted)" }}>Selected Trade:</span>
          <span style={{ color: "var(--text-primary)" }}>
            ${state.backtest.selectedTrade.entry_price.toFixed(2)} → $
            {state.backtest.selectedTrade.exit_price.toFixed(2)}
          </span>
          <span
            style={{
              color:
                state.backtest.selectedTrade.pnl >= 0
                  ? "var(--accent-success)"
                  : "var(--accent-danger)",
            }}
          >
            {state.backtest.selectedTrade.pnl >= 0 ? "+" : ""}$
            {state.backtest.selectedTrade.pnl.toFixed(2)}
          </span>
          <span
            className="text-xs px-2 py-0.5 rounded"
            style={{
              background: "var(--bg-tertiary)",
              color: "var(--text-muted)",
            }}
          >
            {state.backtest.selectedTrade.exit_reason}
          </span>
        </div>
      )}

      {/* Data message footer */}
      {dataMessage && !loading && !error && !state.backtest.selectedTrade && (
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
