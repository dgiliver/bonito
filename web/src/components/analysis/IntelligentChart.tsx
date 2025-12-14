"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createSeriesMarkers,
} from "lightweight-charts";
import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  HistogramData,
  LineData,
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
import { IndicatorRegistry } from "./indicators/registry/IndicatorRegistry";
import "./indicators/registry/registerIndicators"; // Auto-register indicators

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

// Indicator colors
const INDICATOR_COLORS = {
  sma: "#3b82f6", // blue
  ema: "#f97316", // orange
  rsi: "#8b5cf6", // purple
  macd: "#22c55e", // green
  macd_signal: "#ef4444", // red
  macd_hist: "#94a3b8", // gray
  bbands_upper: "#64748b", // slate
  bbands_lower: "#64748b",
  bbands_middle: "#3b82f6",
  vwap: "#06b6d4", // cyan
  atr: "#f59e0b", // amber
};

// ============================================================================
// Indicator Calculations - Now handled by indicator classes
// ============================================================================

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
  // Ref to track candleData for auto-range callback (avoids stale closure)
  const candleDataRef = useRef<CandlestickData<Time>[]>([]);
  // Ref to store volume data for crosshair lookup
  const volumeDataRef = useRef<Map<number, number>>(new Map());
  // Ref to track current range for auto-range callback
  const currentRangeRef = useRef<string>("1Y");

  // Keep refs in sync with state
  useEffect(() => {
    pendingZoomRef.current = pendingZoom;
  }, [pendingZoom]);

  useEffect(() => {
    candleDataRef.current = candleData;
  }, [candleData]);

  useEffect(() => {
    currentRangeRef.current = range;
  }, [range]);

  // Chart refs
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const rsiValueOverlayRef = useRef<HTMLDivElement | null>(null);

  // Indicator registry - manages all indicators
  const indicatorRegistryRef = useRef<IndicatorRegistry>(
    new IndicatorRegistry(),
  );

  // Crosshair tooltip state - dynamic for all indicators
  const [crosshairData, setCrosshairData] = useState<{
    time: string;
    timestamp: number; // Unix timestamp for time-based lookups
    price: number | null; // Price at crosshair Y position (for right-side display)
    ohlc: { open: number; high: number; low: number; close: number } | null; // OHLC at crosshair X position (time)
    volume: number | null; // Volume at crosshair X position (time)
    indicators: Record<string, number | null>; // indicator name -> value at crosshair X position (time)
    activePanel: string | null; // Which panel is currently hovered (e.g., "RSI(14)" or "price")
    activePanelYValue: number | null; // Y-axis value at crosshair position for active panel (for right-side display)
  } | null>(null);

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
        // Trade markers are updated in a separate effect when trades change
      }

      if (volumeSeriesRef.current && data.bars) {
        // Build volume lookup map for crosshair
        const volumeMap = new Map<number, number>();
        data.bars.forEach((bar: OHLCVBar) => {
          volumeMap.set(bar.time, bar.volume);
        });
        volumeDataRef.current = volumeMap;

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
      if (!pendingZoomRef.current) {
        chartRef.current?.timeScale().fitContent();
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
        mode: 0, // CrosshairMode.Normal - free-moving crosshair (not snapped to candles)
        vertLine: { color: "#d4a574", labelBackgroundColor: "#2a2a2a" },
        horzLine: { color: "#d4a574", labelBackgroundColor: "#2a2a2a" },
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
      },
      leftPriceScale: {
        visible: false, // Not used - panel indicators use their own priceScaleId on the right
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
      priceScaleId: "right", // Explicitly set price scale ID for price chart
      lastValueVisible: true, // Show price on right side (Robinhood style)
    });
    const priceScale = candleSeries.priceScale();
    priceScale.applyOptions({
      scaleMargins: { top: 0.05, bottom: 0.15 }, // Price chart uses most of its panel
      borderVisible: true, // Show border to clearly separate scales (Robinhood style)
      borderColor: "rgba(255, 255, 255, 0.1)", // Subtle border
      entireTextOnly: false, // Show all scale labels
      autoScale: true, // Auto-scale based on visible data
      visible: true, // Ensure price scale is visible by default
    });
    // #region agent log
    const initialPriceScaleOptions = priceScale.options();
    fetch("http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        location: "IntelligentChart.tsx:401",
        message: "Price scale INITIAL configuration",
        data: {
          priceScaleId: "right",
          scaleMargins: initialPriceScaleOptions.scaleMargins,
          autoScale: initialPriceScaleOptions.autoScale,
          visible: initialPriceScaleOptions.visible,
          borderVisible: initialPriceScaleOptions.borderVisible,
        },
        timestamp: Date.now(),
        sessionId: "debug-session",
        hypothesisId: "H1",
      }),
    }).catch(() => {});
    // #endregion
    candleSeriesRef.current = candleSeries;

    // Create markers plugin for trade visualization
    const markersPlugin = createSeriesMarkers(candleSeries, []);
    markersPluginRef.current = markersPlugin;

    // Volume series - separate price scale to avoid affecting price chart scale
    // Volume values (millions) would break price scale (hundreds) if shared
    // #region agent log
    fetch("http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        location: "IntelligentChart.tsx:398",
        message: "Creating volume series",
        data: { priceScaleId: "volume" },
        timestamp: Date.now(),
        sessionId: "debug-session",
        hypothesisId: "H1",
      }),
    }).catch(() => {});
    // #endregion
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume", // Separate price scale for volume - creates middle panel
      title: "", // No title widget - volume shown in top-left legend only
      lastValueVisible: false, // Hide automatic last value - shown in top-left legend
    });
    // Initial margins - will be adjusted dynamically when panels are added
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 }, // Volume - will adjust based on panels
      borderVisible: true, // Show border to clearly separate scales (Robinhood style)
      borderColor: "rgba(255, 255, 255, 0.1)", // Subtle border
      entireTextOnly: false, // Show all scale labels
      autoScale: true, // Auto-scale based on visible data
    });
    volumeSeriesRef.current = volumeSeries;

    // #region agent log
    fetch("http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        location: "IntelligentChart.tsx:404",
        message: "Volume series created",
        data: {
          priceScaleId: "volume",
          hasVolumeSeries: !!volumeSeriesRef.current,
        },
        timestamp: Date.now(),
        sessionId: "debug-session",
        hypothesisId: "H3",
      }),
    }).catch(() => {});
    // #endregion

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

    // Handle crosshair move - Robinhood-style free-moving crosshair
    // The cursor IS the crosshair, showing Y-axis value on right and time-based data in top-left
    let lastCrosshairUpdate = 0;
    chart.subscribeCrosshairMove((param) => {
      // Throttle updates to max 30fps (33ms)
      const now = Date.now();
      if (now - lastCrosshairUpdate < 33) return;
      lastCrosshairUpdate = now;

      if (!param.point) {
        setCrosshairData(null);
        return;
      }

      const registry = indicatorRegistryRef.current;
      const yCoord = param.point.y;
      const time = param.time as number | undefined;
      const dateStr = time ? new Date(time * 1000).toLocaleDateString() : "";

      // Helper to find closest candle at timestamp
      const findCandleAtTime = (
        targetTime: number,
      ): CandlestickData<Time> | null => {
        if (candleDataRef.current.length === 0) return null;
        let closest = candleDataRef.current[0];
        let minDiff = Math.abs(
          (candleDataRef.current[0].time as number) - targetTime,
        );
        for (const candle of candleDataRef.current) {
          const diff = Math.abs((candle.time as number) - targetTime);
          if (diff < minDiff) {
            minDiff = diff;
            closest = candle;
          }
        }
        return minDiff < 86400 ? closest : null;
      };

      // Detect which panel the Y coordinate is in
      // Use chart height and scaleMargins to determine panel boundaries
      const chartHeight = chartRef.current?.chartElement().clientHeight || 0;
      const yPercent = (yCoord / chartHeight) * 100;

      let activePanel: string | null = null;
      let activePanelYValue: number | null = null;

      // Check panel indicators first (they're at the bottom)
      // Use coordinateToPrice to detect which panel the Y coordinate is in
      // This is more accurate than using hardcoded percentages
      const panelIndicators = registry.getPanelIndicators();
      for (const panelIndicator of panelIndicators) {
        if (!panelIndicator.isVisible()) continue;
        const priceScaleId = (panelIndicator as any).getPriceScaleId?.();
        if (!priceScaleId) continue;

        // Try to get Y-axis value using coordinateToPrice
        // If this succeeds, we're in this panel's coordinate space
        const series = (panelIndicator as any).getSeries?.();
        if (series && !(series instanceof Map)) {
          try {
            const panelYValue = (
              series as ISeriesApi<"Line">
            ).coordinateToPrice(yCoord);
            // #region agent log
            fetch(
              "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  location: "IntelligentChart.tsx:520",
                  message: "Panel detection - coordinateToPrice",
                  data: {
                    indicatorName: panelIndicator.getName(),
                    priceScaleId,
                    yCoord,
                    yPercent,
                    panelYValue,
                    isValid: panelYValue !== null && !isNaN(panelYValue),
                  },
                  timestamp: Date.now(),
                  sessionId: "debug-session",
                  hypothesisId: "H3",
                }),
              },
            ).catch(() => {});
            // #endregion
            if (panelYValue !== null && !isNaN(panelYValue)) {
              // Successfully got a value - we're in this panel
              activePanel = panelIndicator.getName();
              activePanelYValue = panelYValue;
              break;
            }
          } catch (e) {
            // coordinateToPrice failed - not in this panel's coordinate space
            // #region agent log
            fetch(
              "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  location: "IntelligentChart.tsx:530",
                  message: "Panel detection - coordinateToPrice failed",
                  data: {
                    indicatorName: panelIndicator.getName(),
                    priceScaleId,
                    yCoord,
                    yPercent,
                    error: String(e),
                  },
                  timestamp: Date.now(),
                  sessionId: "debug-session",
                  hypothesisId: "H3",
                }),
              },
            ).catch(() => {});
            // #endregion
          }
        }
      }

      // If not in a panel indicator, we're in the price chart area
      if (!activePanel) {
        activePanel = "price";
        // Get Y-axis price value at crosshair position
        if (candleSeriesRef.current) {
          try {
            activePanelYValue =
              candleSeriesRef.current.coordinateToPrice(yCoord);
          } catch {
            // Fallback: get close price at time
            if (time) {
              const candle = findCandleAtTime(time);
              activePanelYValue = candle?.close || null;
            }
          }
        }
      }

      // Get time-based data (OHLC, Volume, Indicator values) at crosshair X position
      let ohlc: {
        open: number;
        high: number;
        low: number;
        close: number;
      } | null = null;
      let volumeValue: number | null = null;
      const indicatorValues: Record<string, number | null> = {};

      // Try to get time from param, or use closest candle if time is undefined
      let effectiveTime = time;
      if (!effectiveTime && candleDataRef.current.length > 0) {
        // If no time (crosshair between candles), use the most recent candle's time for data lookup
        const lastCandle =
          candleDataRef.current[candleDataRef.current.length - 1];
        effectiveTime = lastCandle.time as number;
      }

      if (effectiveTime) {
        // Get OHLC from candle at this time
        const candle = findCandleAtTime(effectiveTime);
        if (
          candle &&
          "open" in candle &&
          "high" in candle &&
          "low" in candle &&
          "close" in candle
        ) {
          ohlc = {
            open: candle.open,
            high: candle.high,
            low: candle.low,
            close: candle.close,
          };

          // Get volume from volume data ref
          volumeValue = volumeDataRef.current.get(effectiveTime) || null;
          // #region agent log
          fetch(
            "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                location: "IntelligentChart.tsx:590",
                message: "Volume extraction",
                data: {
                  effectiveTime,
                  volumeValue,
                  hasVolumeData: volumeDataRef.current.size > 0,
                },
                timestamp: Date.now(),
                sessionId: "debug-session",
                hypothesisId: "H9",
              }),
            },
          ).catch(() => {});
          // #endregion
        }

        // Get indicator values at this time
        const allIndicators = registry.getAllIndicators();
        for (const indicator of allIndicators) {
          if (!indicator.isVisible()) continue;
          const indicatorName = indicator.getName();
          indicatorValues[indicatorName] =
            indicator.getCrosshairValue(effectiveTime);
        }
      }

      // Control right-side value display based on active panel
      // In Lightweight Charts, each unique priceScaleId creates its own scale on the right
      // We need to ensure the correct scale is visible and shows its value
      if (candleSeriesRef.current && chartRef.current) {
        // #region agent log - BEFORE scale switching
        const priceScaleBefore = candleSeriesRef.current.priceScale();
        const priceScaleOptionsBefore = priceScaleBefore.options();
        const allPanelScalesBefore: Record<string, any> = {};
        for (const panelIndicator of panelIndicators) {
          const panelPriceScaleId = (panelIndicator as any).getPriceScaleId?.();
          if (panelPriceScaleId) {
            try {
              const panelScale = chartRef.current.priceScale(panelPriceScaleId);
              allPanelScalesBefore[panelPriceScaleId] = panelScale.options();
            } catch (e) {
              allPanelScalesBefore[panelPriceScaleId] = { error: String(e) };
            }
          }
        }
        const logDataBefore = {
          location: "IntelligentChart.tsx:621",
          message: "Scale switching - BEFORE",
          data: {
            activePanel,
            panelCount: panelIndicators.length,
            priceScaleVisible: priceScaleOptionsBefore.visible,
            priceScaleAutoScale: priceScaleOptionsBefore.autoScale,
            panelScalesBefore: allPanelScalesBefore,
          },
          timestamp: Date.now(),
          sessionId: "debug-session",
          hypothesisId: "H1,H2",
        };
        console.log("[DEBUG]", logDataBefore);
        fetch(
          "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(logDataBefore),
          },
        ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
        // #endregion

        if (activePanel === "price") {
          // Hovering in price chart - show price value on right
          // #region agent log
          fetch(
            "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                location: "IntelligentChart.tsx:612",
                message: "Price panel active - setting series options",
                data: { activePanel },
                timestamp: Date.now(),
                sessionId: "debug-session",
                hypothesisId: "H1",
              }),
            },
          ).catch(() => {});
          // #endregion
          candleSeriesRef.current.applyOptions({
            lastValueVisible: true,
          });

          // Hide all panel indicator values and scales
          for (const panelIndicator of panelIndicators) {
            const series = (panelIndicator as any).getSeries?.();
            if (series && !(series instanceof Map)) {
              // #region agent log
              fetch(
                "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    location: "IntelligentChart.tsx:620",
                    message: "Hiding panel indicator series",
                    data: { indicatorName: panelIndicator.getName() },
                    timestamp: Date.now(),
                    sessionId: "debug-session",
                    hypothesisId: "H1",
                  }),
                },
              ).catch(() => {});
              // #endregion
              (series as ISeriesApi<"Line">).applyOptions({
                lastValueVisible: false,
              });
            }

            // DO NOT hide panel scales - this breaks the chart
            // Just control lastValueVisible on the series
          }

          // #region agent log
          fetch(
            "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                location: "IntelligentChart.tsx:650",
                message: "Price panel active - series visibility set",
                data: { activePanel },
                timestamp: Date.now(),
                sessionId: "debug-session",
                hypothesisId: "H8",
              }),
            },
          ).catch(() => {});
          // #endregion
        } else {
          // Hovering in a panel indicator - hide price value and scale
          // #region agent log
          fetch(
            "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                location: "IntelligentChart.tsx:655",
                message: "Panel indicator active - setting series options",
                data: { activePanel },
                timestamp: Date.now(),
                sessionId: "debug-session",
                hypothesisId: "H1",
              }),
            },
          ).catch(() => {});
          // #endregion
          candleSeriesRef.current.applyOptions({
            lastValueVisible: false, // Hide price value on right when in panel indicator area
          });

          // #region agent log
          const logDataPriceScale = {
            location: "IntelligentChart.tsx:687",
            message: "Panel active - hiding price lastValue",
            data: { activePanel },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H8",
          };
          console.log(
            "[DEBUG] Panel Active - Hiding Price LastValue",
            logDataPriceScale,
          );
          fetch(
            "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(logDataPriceScale),
            },
          ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
          // #endregion

          // DO NOT hide scales - this breaks the chart
          // Instead, just control lastValueVisible on series

          // Show active panel indicator's value on right
          const activeIndicator = registry.getIndicator(activePanel);
          if (activeIndicator) {
            const series = (activeIndicator as any).getSeries?.();
            if (series && !(series instanceof Map)) {
              // #region agent log
              fetch(
                "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    location: "IntelligentChart.tsx:703",
                    message: "Showing panel indicator series",
                    data: { activePanel, hasSeries: !!series },
                    timestamp: Date.now(),
                    sessionId: "debug-session",
                    hypothesisId: "H1",
                  }),
                },
              ).catch(() => {});
              // #endregion
              (series as ISeriesApi<"Line">).applyOptions({
                lastValueVisible: true, // Show RSI value on right side
              });

              // Get the price scale for this panel indicator and ensure it's visible
              const panelPriceScaleId = (
                activeIndicator as any
              ).getPriceScaleId?.();
              if (panelPriceScaleId && chartRef.current) {
                const panelPriceScale =
                  chartRef.current.priceScale(panelPriceScaleId);
                const panelScaleOptionsBeforeShow = panelPriceScale.options();
                // #region agent log
                fetch(
                  "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
                  {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      location: "IntelligentChart.tsx:715",
                      message: "Showing panel scale - BEFORE",
                      data: {
                        panelPriceScaleId,
                        visibleBefore: panelScaleOptionsBeforeShow.visible,
                        autoScaleBefore: panelScaleOptionsBeforeShow.autoScale,
                        scaleMarginsBefore:
                          panelScaleOptionsBeforeShow.scaleMargins,
                      },
                      timestamp: Date.now(),
                      sessionId: "debug-session",
                      hypothesisId: "H1,H2",
                    }),
                  },
                ).catch(() => {});
                // #endregion

                // Ensure panel scale is configured correctly - DO NOT toggle visibility
                // The panel scale should auto-scale to its data range (0-100 for RSI)
                panelPriceScale.applyOptions({
                  autoScale: true, // Ensure autoScale is true for RSI (0-100 range)
                  scaleMargins: { top: 0.8, bottom: 0 }, // No bottom margin - use full bottom 20%
                });

                const panelScaleOptionsAfterShow = panelPriceScale.options();
                let scaleWidth = 0;
                try {
                  scaleWidth = panelPriceScale.width();
                } catch (e) {
                  // width() might not be available or might throw
                }
                // #region agent log
                fetch(
                  "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
                  {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      location: "IntelligentChart.tsx:730",
                      message: "Showing panel scale - AFTER",
                      data: {
                        panelPriceScaleId,
                        visibleAfter: panelScaleOptionsAfterShow.visible,
                        autoScaleAfter: panelScaleOptionsAfterShow.autoScale,
                        scaleMarginsAfter:
                          panelScaleOptionsAfterShow.scaleMargins,
                        scaleWidth,
                        borderVisible: panelScaleOptionsAfterShow.borderVisible,
                      },
                      timestamp: Date.now(),
                      sessionId: "debug-session",
                      hypothesisId: "H1,H2",
                    }),
                  },
                ).catch(() => {});
                // #endregion
              } else {
                // #region agent log
                fetch(
                  "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
                  {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      location: "IntelligentChart.tsx:705",
                      message: "Panel scale NOT FOUND",
                      data: {
                        activePanel,
                        panelPriceScaleId,
                        hasChart: !!chartRef.current,
                      },
                      timestamp: Date.now(),
                      sessionId: "debug-session",
                      hypothesisId: "H1",
                    }),
                  },
                ).catch(() => {});
                // #endregion
              }
            } else {
              // #region agent log
              fetch(
                "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    location: "IntelligentChart.tsx:710",
                    message: "Panel indicator series NOT FOUND",
                    data: { activePanel, hasIndicator: !!activeIndicator },
                    timestamp: Date.now(),
                    sessionId: "debug-session",
                    hypothesisId: "H1",
                  }),
                },
              ).catch(() => {});
              // #endregion
            }
          } else {
            // #region agent log
            fetch(
              "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  location: "IntelligentChart.tsx:715",
                  message: "Active indicator NOT FOUND in registry",
                  data: {
                    activePanel,
                    registrySize: registry.getAllIndicators().length,
                  },
                  timestamp: Date.now(),
                  sessionId: "debug-session",
                  hypothesisId: "H1",
                }),
              },
            ).catch(() => {});
            // #endregion
          }

          // Hide other panel indicator values
          for (const panelIndicator of panelIndicators) {
            if (panelIndicator.getName() === activePanel) continue;
            const series = (panelIndicator as any).getSeries?.();
            if (series && !(series instanceof Map)) {
              (series as ISeriesApi<"Line">).applyOptions({
                lastValueVisible: false,
              });
            }
          }
        }

        // #region agent log - AFTER scale switching
        const priceScaleAfter = candleSeriesRef.current.priceScale();
        const priceScaleOptionsAfter = priceScaleAfter.options();
        const allPanelScalesAfter: Record<string, any> = {};
        for (const panelIndicator of panelIndicators) {
          const panelPriceScaleId = (panelIndicator as any).getPriceScaleId?.();
          if (panelPriceScaleId) {
            try {
              const panelScale = chartRef.current.priceScale(panelPriceScaleId);
              allPanelScalesAfter[panelPriceScaleId] = panelScale.options();
            } catch (e) {
              allPanelScalesAfter[panelPriceScaleId] = { error: String(e) };
            }
          }
        }
        const logDataAfter = {
          location: "IntelligentChart.tsx:762",
          message: "Scale switching - AFTER",
          data: {
            activePanel,
            priceScaleVisible: priceScaleOptionsAfter.visible,
            priceScaleAutoScale: priceScaleOptionsAfter.autoScale,
            panelScalesAfter: allPanelScalesAfter,
          },
          timestamp: Date.now(),
          sessionId: "debug-session",
          hypothesisId: "H1,H2",
        };
        console.log("[DEBUG]", logDataAfter);
        fetch(
          "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(logDataAfter),
          },
        ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
        // #endregion
      }

      const crosshairPayload = {
        time: dateStr,
        timestamp: time || 0,
        price: activePanelYValue, // Y-axis value at crosshair position (for right-side display)
        ohlc, // OHLC at crosshair X position (time) - for top-left legend
        volume: volumeValue, // Volume at crosshair X position (time) - for top-left legend
        indicators: indicatorValues, // Indicator values at crosshair X position (time) - for top-left legend
        activePanel, // Which panel is active
        activePanelYValue, // Y-axis value for active panel (for right-side display)
      };

      setCrosshairData(crosshairPayload);
    });

    // Handle visible range change - auto-load more data when zooming out
    let lastAutoRangeUpdate = 0;
    chart.timeScale().subscribeVisibleTimeRangeChange((visibleRange) => {
      if (visibleRange) {
        emitChartEvent({
          type: "range_change",
          visibleRange: {
            start: visibleRange.from as number,
            end: visibleRange.to as number,
          },
        });

        // Auto-expand range when user zooms out past data boundaries
        // Throttle to avoid rapid updates
        const now = Date.now();
        if (now - lastAutoRangeUpdate < 500) return; // Reduced throttle for debugging

        // Use refs to get current data (avoids stale closure)
        const currentData = candleDataRef.current;
        if (!currentData || currentData.length === 0) return;

        const dataStart = currentData[0]?.time as number;
        if (!dataStart) return;

        const visibleStart = visibleRange.from as number;

        // If user is at the left edge of data, auto-load more history
        if (visibleStart <= dataStart) {
          lastAutoRangeUpdate = now;

          const rangeOrder = ["1D", "1W", "1M", "3M", "YTD", "1Y", "5Y", "ALL"];
          const currentRangeIndex = rangeOrder.indexOf(currentRangeRef.current);

          if (currentRangeIndex < rangeOrder.length - 1) {
            const newRange = rangeOrder[currentRangeIndex + 1];
            window.dispatchEvent(
              new CustomEvent("chart-auto-range", {
                detail: { range: newRange },
              }),
            );
          }
        }
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

    requestAnimationFrame(() => {
      if (chartRef.current) {
        chartRef.current.timeScale().setVisibleRange({
          from: zoomStart as Time,
          to: zoomEnd as Time,
        });
      }
    });
  }, [selectedTrade, candleData]);

  // ============================================================================
  // Indicator Rendering
  // ============================================================================

  // Render indicators when data or indicator config changes (Using Registry Pattern)
  useEffect(() => {
    if (!chartRef.current || candleData.length === 0) return;

    const chart = chartRef.current;
    const registry = indicatorRegistryRef.current;

    // Small delay to ensure chart data is fully rendered
    const timeoutId = setTimeout(() => {
      if (!chartRef.current) return;

      // Use ref to get LATEST candleData (avoid stale closure)
      const currentCandleData = candleDataRef.current;
      if (currentCandleData.length === 0) return;

      // Track which indicators should exist
      const activeIndicatorNames = new Set(
        state.chart.indicators.filter((i) => i.visible).map((i) => i.name),
      );

      // Remove indicators that are no longer active
      const allIndicators = registry.getAllIndicators();
      for (const indicator of allIndicators) {
        if (!activeIndicatorNames.has(indicator.getName())) {
          indicator.cleanup(chart);
          registry.removeIndicator(indicator.getName());
        }
      }

      // Add/update active indicators
      for (const indicatorConfig of state.chart.indicators) {
        if (!indicatorConfig.visible) continue;

        let indicator = registry.getIndicator(indicatorConfig.name);

        if (!indicator) {
          // Create new indicator
          indicator = registry.addIndicator(indicatorConfig);
          // #region agent log
          fetch(
            "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                location: "IntelligentChart.tsx:708",
                message: "Creating indicator",
                data: {
                  type: indicatorConfig.type,
                  name: indicatorConfig.name,
                  created: !!indicator,
                  isPanel: indicatorConfig.type.toLowerCase() === "rsi",
                  hasGetPriceScaleId: indicator
                    ? !!(indicator as any).getPriceScaleId
                    : false,
                  priceScaleId: indicator
                    ? (indicator as any).getPriceScaleId?.()
                    : "N/A",
                },
                timestamp: Date.now(),
                sessionId: "debug-session",
                hypothesisId: "H1,H5",
              }),
            },
          ).catch(() => {});
          // #endregion
          if (!indicator) continue; // Failed to create (unregistered type)

          // Set candle data ref for Bollinger Bands (needs full candle data)
          if (
            indicatorConfig.type.toLowerCase() === "bbands" ||
            indicatorConfig.type.toLowerCase() === "bollinger"
          ) {
            const bbIndicator = indicator as any;
            if (bbIndicator.setCandleDataRef) {
              bbIndicator.setCandleDataRef(candleDataRef);
            }
          }
        }

        // Calculate and render indicator
        const calculatedData = indicator.calculate(currentCandleData);
        indicator.updateData(calculatedData);
        const priceScaleId = (indicator as any).getPriceScaleId?.() || "N/A";

        // Calculate data range for verification
        const minValue =
          calculatedData.length > 0
            ? Math.min(...calculatedData.map((d) => d.value))
            : null;
        const maxValue =
          calculatedData.length > 0
            ? Math.max(...calculatedData.map((d) => d.value))
            : null;

        // #region agent log
        const logData1 = {
          location: "IntelligentChart.tsx:1001",
          message: "Rendering indicator - BEFORE",
          data: {
            name: indicatorConfig.name,
            type: indicatorConfig.type,
            dataPoints: calculatedData.length,
            priceScaleId,
            minValue,
            maxValue,
            firstValue: calculatedData[0]?.value,
            lastValue: calculatedData[calculatedData.length - 1]?.value,
            priceDataMin:
              currentCandleData.length > 0
                ? Math.min(...currentCandleData.map((d) => d.close))
                : null,
            priceDataMax:
              currentCandleData.length > 0
                ? Math.max(...currentCandleData.map((d) => d.close))
                : null,
          },
          timestamp: Date.now(),
          sessionId: "debug-session",
          hypothesisId: "H2",
        };
        console.log("[DEBUG]", logData1);
        fetch(
          "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(logData1),
          },
        ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
        // #endregion

        indicator.render(chart, calculatedData);

        // CRITICAL: After rendering a panel indicator, immediately configure scale visibility
        // This ensures the correct scale is visible when the indicator is first added
        const isPanelIndicator =
          (indicator as any).getPriceScaleId &&
          priceScaleId !== "right" &&
          priceScaleId !== "N/A" &&
          priceScaleId !== "volume";
        if (isPanelIndicator && chartRef.current && candleSeriesRef.current) {
          // #region agent log
          console.log(
            "[DEBUG] Panel indicator rendered, configuring initial scale visibility",
            { indicatorName: indicatorConfig.name, priceScaleId },
          );
          // #endregion

          // HYPOTHESIS: In Lightweight Charts, overlay scales (custom priceScaleIds) might need
          // the base "right" scale to be visible to render properly. The overlay scale shares
          // the same visual space as the right scale but shows different values.
          // We'll keep the right scale visible but ensure the panel scale is configured correctly
          const priceScale = candleSeriesRef.current.priceScale();
          const priceScaleOptionsBefore = priceScale.options();
          // #region agent log
          const logData2 = {
            location: "IntelligentChart.tsx:1015",
            message: "Initial scale config after panel add - BEFORE",
            data: {
              indicatorName: indicatorConfig.name,
              priceScaleId,
              priceScaleVisible: priceScaleOptionsBefore.visible,
              priceScaleAutoScale: priceScaleOptionsBefore.autoScale,
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H1",
          };
          console.log("[DEBUG]", logData2);
          fetch(
            "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(logData2),
            },
          ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
          // #endregion

          // Keep price scale visible - overlay scales might need it to render
          // We'll control which values are shown via lastValueVisible instead
          priceScale.applyOptions({
            visible: true, // Keep visible for overlay scales to work
          });

          const panelPriceScale = chartRef.current.priceScale(priceScaleId);
          const panelScaleOptionsBefore = panelPriceScale.options();
          let panelScaleWidthBefore = 0;
          try {
            panelScaleWidthBefore = panelPriceScale.width();
          } catch (e) {
            // width() might not be available
          }
          // #region agent log
          const logData3 = {
            location: "IntelligentChart.tsx:1025",
            message:
              "Initial scale config after panel add - Panel scale BEFORE",
            data: {
              indicatorName: indicatorConfig.name,
              priceScaleId,
              panelScaleVisible: panelScaleOptionsBefore.visible,
              panelScaleAutoScale: panelScaleOptionsBefore.autoScale,
              panelScaleWidth: panelScaleWidthBefore,
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H1",
          };
          console.log("[DEBUG]", logData3);
          fetch(
            "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(logData3),
            },
          ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
          // #endregion

          panelPriceScale.applyOptions({
            visible: true, // Show panel scale when panel indicator is added
            autoScale: true, // Ensure autoScale is true
          });

          let panelScaleWidthAfter = 0;
          try {
            panelScaleWidthAfter = panelPriceScale.width();
          } catch (e) {
            // width() might not be available
          }

          const priceScaleOptionsAfter = priceScale.options();
          const panelScaleOptionsAfter = panelPriceScale.options();
          // #region agent log
          const logData4 = {
            location: "IntelligentChart.tsx:1045",
            message: "Initial scale config after panel add - AFTER",
            data: {
              indicatorName: indicatorConfig.name,
              priceScaleId,
              priceScaleVisible: priceScaleOptionsAfter.visible,
              priceScaleAutoScale: priceScaleOptionsAfter.autoScale,
              panelScaleVisible: panelScaleOptionsAfter.visible,
              panelScaleAutoScale: panelScaleOptionsAfter.autoScale,
              panelScaleWidth: panelScaleWidthAfter,
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H1",
          };
          console.log("[DEBUG]", logData4);
          fetch(
            "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(logData4),
            },
          ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
          // #endregion
        }

        // Verify price scale is properly configured after rendering
        if (
          priceScaleId &&
          priceScaleId !== "N/A" &&
          priceScaleId !== "right"
        ) {
          const series = (indicator as any).getSeries?.();
          if (series && !(series instanceof Map)) {
            const priceScale = (series as ISeriesApi<"Line">).priceScale();
            const scaleOptions = priceScale.options();

            // Get all price scales from chart to verify separation
            const allPriceScales: string[] = [];
            try {
              // Try to get all scales (Lightweight Charts doesn't expose this directly)
              // We'll check by trying to access the scale
              const scaleWidth = priceScale.width();
              // #region agent log
              fetch(
                "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    location: "IntelligentChart.tsx:862",
                    message: "Panel scale AFTER render",
                    data: {
                      priceScaleId,
                      scaleWidth,
                      scaleMargins: scaleOptions.scaleMargins,
                      borderVisible: scaleOptions.borderVisible,
                      autoScale: scaleOptions.autoScale,
                      indicatorMinValue: minValue,
                      indicatorMaxValue: maxValue,
                      priceMinValue:
                        currentCandleData.length > 0
                          ? Math.min(...currentCandleData.map((d) => d.close))
                          : null,
                      priceMaxValue:
                        currentCandleData.length > 0
                          ? Math.max(...currentCandleData.map((d) => d.close))
                          : null,
                    },
                    timestamp: Date.now(),
                    sessionId: "debug-session",
                    hypothesisId: "H2",
                  }),
                },
              ).catch(() => {});
              // #endregion
            } catch (e) {
              // #region agent log
              fetch(
                "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    location: "IntelligentChart.tsx:870",
                    message: "Panel scale error",
                    data: { priceScaleId, error: String(e) },
                    timestamp: Date.now(),
                    sessionId: "debug-session",
                    hypothesisId: "H2",
                  }),
                },
              ).catch(() => {});
              // #endregion
            }
          }
        }
      }

      // Dynamically adjust price/volume margins based on panel indicators
      const panelIndicators = registry.getPanelIndicators();
      const hasPanels = panelIndicators.length > 0;

      // #region agent log
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: "IntelligentChart.tsx:777",
            message: "Adjusting margins",
            data: {
              hasPanels,
              panelCount: panelIndicators.length,
              panelNames: panelIndicators.map((p) => p.getName()),
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H1",
          }),
        },
      ).catch(() => {});
      // #endregion

      // In Lightweight Charts, each unique priceScaleId creates a separate panel
      // Panels stack vertically in the order they are created
      // scaleMargins control how much of EACH panel's vertical space is used
      // We need to ensure panels don't overlap by setting appropriate margins

      if (candleSeriesRef.current) {
        // Price chart panel (top) - uses top portion of chart
        // scaleMargins are relative to ENTIRE chart height
        // When panels exist: price uses top 60% (0% to 65% of chart, leaving room for volume/RSI)
        // When no panels: price uses top 80% (0% to 85% of chart)
        candleSeriesRef.current.priceScale().applyOptions({
          scaleMargins: {
            top: 0.05,
            bottom: hasPanels ? 0.35 : 0.15, // Leave 35% for volume+RSI when panels exist, 15% for volume when not
          },
        });
      }

      if (volumeSeriesRef.current) {
        // Volume panel (middle) - positioned between price and RSI
        // scaleMargins are relative to ENTIRE chart height
        // When panels exist: volume uses middle section (65% to 80% of chart)
        // When no panels: volume uses bottom section (85% to 100% of chart)
        volumeSeriesRef.current.priceScale().applyOptions({
          scaleMargins: {
            top: hasPanels ? 0.65 : 0.85, // Start at 65% when panels exist, 85% when not
            bottom: hasPanels ? 0.2 : 0, // Leave 20% for RSI below when panels exist
          },
        });
      }

      // Panel indicators use their own priceScaleId on the right side
      // Each panel's scale auto-scales to its own data range (0-100 for RSI)
      // We don't need to show/hide scales - just let them coexist
      // #region agent log
      const logDataPanels = {
        location: "IntelligentChart.tsx:1150",
        message: "Panel configuration",
        data: { hasPanels, panelCount: panelIndicators.length },
        timestamp: Date.now(),
        sessionId: "debug-session",
        hypothesisId: "H8",
      };
      console.log("[DEBUG] Panel Configuration", logDataPanels);
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(logDataPanels),
        },
      ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
      // #endregion
    }, 100); // Delay to ensure chart data is fully rendered

    return () => clearTimeout(timeoutId);
  }, [state.chart.indicators, candleData]);

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

  // Listen for auto-range events (triggered when user zooms out past data)
  useEffect(() => {
    const handleAutoRange = (e: Event) => {
      const customEvent = e as CustomEvent<{ range: string }>;
      const newRange = customEvent.detail.range;
      if (newRange && newRange !== range && !isIntraday) {
        setRange(newRange);
        localStorage.setItem("chart-range", newRange);
      }
    };

    window.addEventListener("chart-auto-range", handleAutoRange);
    return () =>
      window.removeEventListener("chart-auto-range", handleAutoRange);
  }, [range, isIntraday]);

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
      dispatch({ type: "SET_SYMBOL", symbol: backtestResult.symbol });
    }

    const startDate = new Date(backtestResult.period.start);
    const endDate = new Date(backtestResult.period.end);
    const now = new Date();

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

    // Calculate zoom range with padding
    const startTs = Math.floor(startDate.getTime() / 1000);
    const endTs = Math.floor(endDate.getTime() / 1000);
    const padding = (endTs - startTs) * 0.05;
    const zoomRange = { start: startTs - padding, end: endTs + padding };

    // Update range if needed - this will trigger a data fetch
    if (newRange !== range && !isIntraday) {
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

      if (zStart < zEnd) {
        requestAnimationFrame(() => {
          if (chartRef.current) {
            chartRef.current.timeScale().setVisibleRange({
              from: zStart as Time,
              to: zEnd as Time,
            });
          }
        });
      }
      setPendingZoom(null);
    }
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

    // Calculate intersection
    const zoomStart = Math.max(dataStart, pendingZoom.start);
    const zoomEnd = Math.min(dataEnd, pendingZoom.end);

    if (zoomStart < zoomEnd) {
      requestAnimationFrame(() => {
        if (chartRef.current) {
          chartRef.current.timeScale().setVisibleRange({
            from: zoomStart as Time,
            to: zoomEnd as Time,
          });
        }
      });
      setPendingZoom(null);
    }
    // If no overlap, keep pendingZoom - retry when fresh data arrives
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
            // Expand data range to 5Y when adding indicators to ensure full coverage
            if (range !== "5Y" && range !== "ALL" && !isIntraday) {
              setRange("5Y");
              localStorage.setItem("chart-range", "5Y");
            }
            dispatch({ type: "ADD_INDICATOR", indicator: intent.indicator });
          }
          break;

        case "annotate":
          if (intent.annotation) {
            const annotation = {
              ...intent.annotation,
              id: crypto.randomUUID(),
            };
            dispatch({ type: "ADD_ANNOTATION", annotation });
          }
          break;

        case "highlight":
          if (intent.highlightRange) {
            const highlight = {
              id: crypto.randomUUID(),
              type: "region" as const,
              timestamp: intent.highlightRange.start,
              endTimestamp: intent.highlightRange.end,
              color: intent.highlightRange.color,
            };
            dispatch({ type: "ADD_ANNOTATION", annotation: highlight });
          }
          break;

        case "clear":
          if (
            intent.clearType === "annotations" ||
            intent.clearType === "all"
          ) {
            dispatch({ type: "CLEAR_ANNOTATIONS" });
          }
          if (intent.clearType === "indicators" || intent.clearType === "all") {
            const registry = indicatorRegistryRef.current;
            const chart = chartRef.current;

            // Check if we're clearing a specific indicator or all
            const specificIndicator = (intent as { indicatorName?: string })
              .indicatorName;

            if (specificIndicator && chart) {
              // Remove only the specific indicator
              const indicator = registry.getIndicator(specificIndicator);
              if (indicator) {
                indicator.cleanup(chart);
                registry.removeIndicator(specificIndicator);
                dispatch({ type: "REMOVE_INDICATOR", name: specificIndicator });
              }
            } else if (chart) {
              // Clear all indicators
              const allIndicators = registry.getAllIndicators();
              for (const indicator of allIndicators) {
                indicator.cleanup(chart);
              }
              registry.clear();

              // Dispatch remove for all indicators in state
              state.chart.indicators.forEach((ind) => {
                dispatch({ type: "REMOVE_INDICATOR", name: ind.name });
              });
            }
          }
          break;
      }

      processIntent(intent.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Intentionally excluding state.chart.indicators to avoid infinite loop
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

        {/* Crosshair Tooltip - shows values at hover position */}
        {crosshairData && (
          <div
            className="absolute top-2 left-2 z-20 px-3 py-2.5 rounded-lg text-xs max-h-64 overflow-y-auto"
            style={{
              color: "var(--text-primary)",
            }}
          >
            {/* #region agent log */}
            {(() => {
              fetch(
                "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    location: "IntelligentChart.tsx:1310",
                    message: "Rendering crosshair tooltip",
                    data: {
                      hasCrosshairData: !!crosshairData,
                      volume: crosshairData.volume,
                      indicatorCount: Object.keys(crosshairData.indicators)
                        .length,
                      indicatorNames: Object.keys(crosshairData.indicators),
                    },
                    timestamp: Date.now(),
                    sessionId: "debug-session",
                    hypothesisId: "H4",
                  }),
                },
              ).catch(() => {});
              return null;
            })()}
            {/* #endregion */}
            {/* Robinhood-style legend: OHLC + Volume + Overlay indicators for main chart */}
            {(crosshairData.ohlc || crosshairData.volume !== null) && (
              <div className="mb-2 space-y-1">
                {/* OHLCV displayed inline: O H L C V */}
                {crosshairData.ohlc &&
                  (() => {
                    // Determine if candle is green (close > open) or red (close < open)
                    const isGreen =
                      crosshairData.ohlc.close >= crosshairData.ohlc.open;
                    const numberColor = isGreen ? "#22c55e" : "#ef4444"; // green-500 or red-500

                    // Format volume for display
                    const formatVolume = (vol: number | null) => {
                      if (vol === null) return null;
                      if (vol >= 1000000)
                        return `${(vol / 1000000).toFixed(2)}M`;
                      if (vol >= 1000) return `${(vol / 1000).toFixed(2)}K`;
                      return vol.toFixed(0);
                    };

                    return (
                      <div className="flex items-center gap-2 text-xs">
                        <span style={{ color: "#000000" }}>O</span>
                        <span
                          className="font-mono font-semibold"
                          style={{ color: numberColor }}
                        >
                          {crosshairData.ohlc.open.toFixed(2)}
                        </span>
                        <span style={{ color: "#000000" }}>H</span>
                        <span
                          className="font-mono font-semibold"
                          style={{ color: numberColor }}
                        >
                          {crosshairData.ohlc.high.toFixed(2)}
                        </span>
                        <span style={{ color: "#000000" }}>L</span>
                        <span
                          className="font-mono font-semibold"
                          style={{ color: numberColor }}
                        >
                          {crosshairData.ohlc.low.toFixed(2)}
                        </span>
                        <span style={{ color: "#000000" }}>C</span>
                        <span
                          className="font-mono font-semibold"
                          style={{ color: numberColor }}
                        >
                          {crosshairData.ohlc.close.toFixed(2)}
                        </span>
                        {crosshairData.volume !== null && (
                          <>
                            <span style={{ color: "#000000" }}>V</span>
                            <span
                              className="font-mono font-semibold"
                              style={{ color: numberColor }}
                            >
                              {formatVolume(crosshairData.volume)}
                            </span>
                          </>
                        )}
                      </div>
                    );
                  })()}
              </div>
            )}
            {/* Show overlay indicator values (not panel indicators - they show in their own panel) */}
            {Object.entries(crosshairData.indicators).map(([name, value]) => {
              if (value === null) return null;

              // Skip panel indicators - they display in their own panel's top-left
              const panelIndicators =
                indicatorRegistryRef.current?.getPanelIndicators() || [];
              const isPanelIndicator = panelIndicators.some(
                (ind) => ind.getName() === name,
              );
              if (isPanelIndicator) return null;

              // Get indicator config for threshold info
              const indicator = state.chart.indicators.find(
                (i) => i.name === name,
              );
              const indType = indicator?.type.toLowerCase() || "";

              // Determine color based on indicator type and thresholds
              let color = "var(--text-primary)";
              let suffix = "";
              let bgColor: string | undefined = undefined;

              if (indType === "rsi") {
                // Always show RSI value, color-code based on thresholds
                const overbought =
                  (indicator?.params.overbought as number) || 70;
                const oversold = (indicator?.params.oversold as number) || 30;
                if (value >= overbought) {
                  color = "#ef4444"; // red-500
                  bgColor = "rgba(239, 68, 68, 0.1)";
                  suffix = " Overbought";
                } else if (value <= oversold) {
                  color = "#22c55e"; // green-500
                  bgColor = "rgba(34, 197, 94, 0.1)";
                  suffix = " Oversold";
                } else {
                  // Neutral RSI - use indicator color
                  color = INDICATOR_COLORS.rsi || "#8b5cf6";
                  bgColor = "rgba(139, 92, 246, 0.1)";
                }
              } else if (indType === "sma" || indType === "ema") {
                // Moving averages - compare to price for trend
                if (crosshairData.price && value > crosshairData.price) {
                  color = "#22c55e"; // green - above price (bullish)
                  bgColor = "rgba(34, 197, 94, 0.1)";
                } else if (crosshairData.price && value < crosshairData.price) {
                  color = "#ef4444"; // red - below price (bearish)
                  bgColor = "rgba(239, 68, 68, 0.1)";
                } else {
                  color =
                    (INDICATOR_COLORS as Record<string, string>)[indType] ||
                    "var(--text-primary)";
                  bgColor = "rgba(0, 0, 0, 0.05)";
                }
              } else if (indType === "stoch" || indType === "stochastic") {
                if (value >= 80) {
                  color = "#ef4444";
                  bgColor = "rgba(239, 68, 68, 0.1)";
                  suffix = " Overbought";
                } else if (value <= 20) {
                  color = "#22c55e";
                  bgColor = "rgba(34, 197, 94, 0.1)";
                  suffix = " Oversold";
                } else {
                  color =
                    (INDICATOR_COLORS as Record<string, string>)[indType] ||
                    "var(--text-primary)";
                  bgColor = "rgba(0, 0, 0, 0.05)";
                }
              } else {
                // Default indicator color
                color =
                  (INDICATOR_COLORS as Record<string, string>)[indType] ||
                  "var(--text-primary)";
                bgColor = "rgba(0, 0, 0, 0.05)";
              }

              return (
                <div
                  key={name}
                  className="flex items-center justify-between gap-3 mb-1.5 px-2 py-1 rounded"
                  style={{ background: bgColor }}
                >
                  <span
                    className="text-xs font-medium"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {name}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span
                      className="font-mono font-semibold text-sm"
                      style={{ color }}
                    >
                      {value.toFixed(2)}
                    </span>
                    {suffix && (
                      <span
                        className="text-xs font-medium"
                        style={{ color, opacity: 0.8 }}
                      >
                        {suffix}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div ref={chartContainerRef} className="w-full h-full relative">
          {/* Panel background overlays - add subtle hue to distinguish panels (especially RSI) */}
          {indicatorRegistryRef.current &&
            (() => {
              const panelIndicators =
                indicatorRegistryRef.current.getPanelIndicators();
              return panelIndicators.map((indicator) => {
                const priceScaleId =
                  (indicator as any).getPriceScaleId?.() || "";
                const indicatorType = indicator.getType().toLowerCase();

                // Calculate panel position
                let topPercent = 80; // Default for RSI
                const panelPositions: Record<string, number> = {
                  rsi: 80,
                  macd: 80,
                  stoch: 80,
                  adx: 80,
                  atr: 80,
                };
                topPercent = panelPositions[priceScaleId] || 80;

                // Remove full-panel background - threshold zone is handled by RSI indicator itself
                // The RSI indicator will render a shaded area between 30-70 using AreaSeries
                return null;
              });
            })()}

          {/* Panel indicator labels - show in top-left of each panel (Robinhood style) */}
          {indicatorRegistryRef.current &&
            crosshairData &&
            (() => {
              const panelIndicators =
                indicatorRegistryRef.current.getPanelIndicators();
              return panelIndicators.map((indicator) => {
                const indicatorName = indicator.getName();
                // Get value at crosshair X position (time), not Y position
                const indicatorValue =
                  crosshairData.indicators[indicatorName] ?? null;
                const isActive = crosshairData.activePanel === indicatorName;

                // Calculate vertical position based on panel's scaleMargins
                // RSI panel starts at 80% (scaleMargins.top = 0.8)
                const priceScaleId =
                  (indicator as any).getPriceScaleId?.() || "";
                let topPercent = 80; // Default for RSI

                // Map price scale IDs to their panel start positions (from scaleMargins.top)
                const panelPositions: Record<string, number> = {
                  rsi: 80,
                  macd: 80,
                  stoch: 80,
                  adx: 80,
                  atr: 80,
                };

                topPercent = panelPositions[priceScaleId] || 80;

                // Position label at top of panel (slightly above the panel start for visibility)
                const labelTop = Math.max(0, topPercent - 1.5);

                return (
                  <div
                    key={indicatorName}
                    className="absolute left-2 z-30 px-2 py-1 rounded text-xs"
                    style={{
                      top: `${labelTop}%`,
                      background: isActive
                        ? "rgba(139, 92, 246, 0.15)"
                        : "rgba(0, 0, 0, 0.4)",
                      backdropFilter: "blur(4px)",
                      color: "var(--text-primary)",
                      border: `1px solid ${isActive ? "rgba(139, 92, 246, 0.3)" : "rgba(255, 255, 255, 0.08)"}`,
                      transition: "all 0.15s ease",
                    }}
                  >
                    <span
                      className="font-medium"
                      style={{
                        color: isActive ? "#8b5cf6" : "var(--text-muted)",
                      }}
                    >
                      {indicatorName}
                    </span>
                    {indicatorValue !== null && (
                      <>
                        <span
                          className="mx-1.5"
                          style={{ color: "var(--text-muted)", opacity: 0.6 }}
                        >
                          ·
                        </span>
                        <span
                          className="font-mono font-semibold"
                          style={{
                            color: isActive ? "#8b5cf6" : "var(--text-primary)",
                          }}
                        >
                          {indicatorValue.toFixed(2)}
                        </span>
                      </>
                    )}
                  </div>
                );
              });
            })()}
        </div>
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
