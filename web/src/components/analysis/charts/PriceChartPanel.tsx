"use client";

/**
 * PriceChartPanel - Main price chart with candlesticks, volume, and overlay indicators
 */

import React, {
  useRef,
  useEffect,
  useState,
  forwardRef,
  useImperativeHandle,
} from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createSeriesMarkers,
} from "lightweight-charts";
import type {
  ISeriesApi,
  Time,
  CandlestickData,
  HistogramData,
  LineData,
  DeepPartial,
  ChartOptions,
  SeriesMarker,
  ISeriesMarkersPluginApi,
} from "lightweight-charts";
import {
  BaseChartPanel,
  ChartPanelConfig,
  CrosshairData,
  CrosshairMoveCallback,
  TimeRangeChangeCallback,
  CrosshairMode,
} from "./BaseChartPanel";

// Types
export interface OHLCVData {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface OverlayIndicatorData {
  name: string;
  type: string;
  color: string;
  data: LineData<Time>[];
  lineWidth?: number;
}

export interface PriceChartData {
  candles: OHLCVData[];
  overlays?: OverlayIndicatorData[];
}

export interface PriceChartLegendData {
  time: Time | null;
  ohlc: { open: number; high: number; low: number; close: number } | null;
  volume: number | null;
  overlays: { name: string; value: number; color: string }[];
}

export interface PriceChartPanelRef {
  initialize: (
    container: HTMLDivElement,
    options?: DeepPartial<ChartOptions>,
  ) => void;
  updateData: (data: PriceChartData) => void;
  setOnCrosshairMove: (callback: CrosshairMoveCallback) => void;
  setOnTimeRangeChange: (callback: TimeRangeChangeCallback) => void;
  syncCrosshair: (data: CrosshairData) => void;
  syncTimeRange: (range: any) => void;
  resize: (width: number, height: number) => void;
  fitContent: () => void;
  cleanup: () => void;
  getChart: () => any;
  getLegendData: (time: Time) => PriceChartLegendData;
  setMarkers: (markers: SeriesMarker<Time>[]) => void;
  addOverlay: (indicator: OverlayIndicatorData) => void;
  removeOverlay: (name: string) => void;
  setCrosshairMode: (mode: CrosshairMode) => void;
  setHorzLineLabelVisible: (visible: boolean) => void;
  setTimeScaleVisible: (visible: boolean) => void;
}

// PriceChartPanelImpl - Class implementation
class PriceChartPanelImpl extends BaseChartPanel {
  private candleSeries: ISeriesApi<"Candlestick"> | null = null;
  private volumeSeries: ISeriesApi<"Histogram"> | null = null;
  private overlaySeries: Map<string, ISeriesApi<"Line">> = new Map();
  private markersPlugin: ISeriesMarkersPluginApi<Time> | null = null;
  private candleData: OHLCVData[] = [];
  private overlayData: Map<string, OverlayIndicatorData> = new Map();
  private showVolume: boolean = true;

  constructor(config: ChartPanelConfig, showVolume: boolean = true) {
    super("price", config);
    this.showVolume = showVolume;
  }

  protected onInitialize(): void {
    if (!this.chart) return;

    // Create candlestick series using v5 API
    this.candleSeries = this.chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      priceScaleId: "right",
      lastValueVisible: true,
      priceLineVisible: true,
    });

    // Create markers plugin for trade markers
    this.markersPlugin = createSeriesMarkers(this.candleSeries);

    if (this.showVolume) {
      this.volumeSeries = this.chart.addSeries(HistogramSeries, {
        color: "#26a69a",
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
        lastValueVisible: false,
      });

      this.chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
        visible: false,
      });
    }
  }

  getMainSeries(): ISeriesApi<"Candlestick"> | null {
    return this.candleSeries;
  }

  /**
   * Get the close price at a specific time
   */
  protected getValueAtTime(time: Time): number | null {
    const timeNum =
      typeof time === "number"
        ? time
        : new Date(time as string).getTime() / 1000;

    // Find exact or closest candle
    let closest: OHLCVData | null = null;
    let minDiff = Infinity;

    for (const candle of this.candleData) {
      const candleTimeNum =
        typeof candle.time === "number"
          ? candle.time
          : new Date(candle.time as string).getTime() / 1000;
      const diff = Math.abs(candleTimeNum - timeNum);
      if (diff < minDiff) {
        minDiff = diff;
        closest = candle;
      }
    }

    return closest?.close ?? null;
  }

  updateData(data: PriceChartData): void {
    if (!this.chart || !this.candleSeries) return;

    this.candleData = data.candles;

    const candleChartData: CandlestickData<Time>[] = data.candles.map((c) => ({
      time: c.time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    this.candleSeries.setData(candleChartData);

    if (this.volumeSeries && this.showVolume) {
      const volumeChartData: HistogramData<Time>[] = data.candles
        .filter((c) => c.volume !== undefined)
        .map((c) => ({
          time: c.time,
          value: c.volume!,
          color:
            c.close >= c.open
              ? "rgba(34, 197, 94, 0.5)"
              : "rgba(239, 68, 68, 0.5)",
        }));

      this.volumeSeries.setData(volumeChartData);
    }

    if (data.overlays) {
      this.updateOverlays(data.overlays);
    }
  }

  private updateOverlays(overlays: OverlayIndicatorData[]): void {
    if (!this.chart) return;

    const activeNames = new Set(overlays.map((o) => o.name));

    for (const [name, series] of this.overlaySeries) {
      if (!activeNames.has(name)) {
        this.chart.removeSeries(series);
        this.overlaySeries.delete(name);
        this.overlayData.delete(name);
      }
    }

    for (const overlay of overlays) {
      let series = this.overlaySeries.get(overlay.name);

      if (!series) {
        series = this.chart.addSeries(LineSeries, {
          color: overlay.color,
          lineWidth: (overlay.lineWidth ?? 2) as 1 | 2 | 3 | 4,
          priceScaleId: "right",
          lastValueVisible: false,
          priceLineVisible: false,
        });
        this.overlaySeries.set(overlay.name, series);
      }

      series.setData(overlay.data);
      this.overlayData.set(overlay.name, overlay);
    }
  }

  addOverlay(indicator: OverlayIndicatorData): void {
    if (!this.chart) return;

    let series = this.overlaySeries.get(indicator.name);

    if (!series) {
      series = this.chart.addSeries(LineSeries, {
        color: indicator.color,
        lineWidth: (indicator.lineWidth ?? 2) as 1 | 2 | 3 | 4,
        priceScaleId: "right",
        lastValueVisible: false,
        priceLineVisible: false,
      });
      this.overlaySeries.set(indicator.name, series);
    }

    series.setData(indicator.data);
    this.overlayData.set(indicator.name, indicator);
  }

  removeOverlay(name: string): void {
    if (!this.chart) return;

    const series = this.overlaySeries.get(name);
    if (series) {
      this.chart.removeSeries(series);
      this.overlaySeries.delete(name);
      this.overlayData.delete(name);
    }
  }

  setMarkers(markers: SeriesMarker<Time>[]): void {
    if (!this.markersPlugin) return;
    this.markersPlugin.setMarkers(markers);
  }

  getCrosshairValue(time: Time): OHLCVData | null {
    const candle = this.candleData.find((c) => c.time === time);
    return candle || null;
  }

  getLegendData(time: Time): PriceChartLegendData {
    const result: PriceChartLegendData = {
      time,
      ohlc: null,
      volume: null,
      overlays: [],
    };

    const candle = this.findCandleAtTime(time);
    if (candle) {
      result.ohlc = {
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      };
      result.volume = candle.volume ?? null;
    }

    for (const [name, overlay] of this.overlayData) {
      const dataPoint = overlay.data.find((d) => d.time === time);
      if (dataPoint && dataPoint.value !== undefined) {
        result.overlays.push({
          name,
          value: dataPoint.value,
          color: overlay.color,
        });
      }
    }

    return result;
  }

  private findCandleAtTime(time: Time): OHLCVData | null {
    const exactMatch = this.candleData.find((c) => c.time === time);
    if (exactMatch) return exactMatch;

    if (this.candleData.length === 0) return null;

    const timeNum =
      typeof time === "number"
        ? time
        : new Date(time as string).getTime() / 1000;

    let closest = this.candleData[0];
    let minDiff = Math.abs(
      (typeof closest.time === "number"
        ? closest.time
        : new Date(closest.time as string).getTime() / 1000) - timeNum,
    );

    for (const candle of this.candleData) {
      const candleTimeNum =
        typeof candle.time === "number"
          ? candle.time
          : new Date(candle.time as string).getTime() / 1000;
      const diff = Math.abs(candleTimeNum - timeNum);
      if (diff < minDiff) {
        minDiff = diff;
        closest = candle;
      }
    }

    return closest;
  }

  cleanup(): void {
    this.candleSeries = null;
    this.volumeSeries = null;
    this.markersPlugin = null;
    this.overlaySeries.clear();
    this.candleData = [];
    this.overlayData.clear();
    super.cleanup();
  }
}

// React Component Wrapper
interface PriceChartPanelProps {
  height: number;
  showVolume?: boolean;
  showTimeScale?: boolean; // Whether to show the time scale (dates) at bottom
  className?: string;
}

export const PriceChartPanel = forwardRef<
  PriceChartPanelRef,
  PriceChartPanelProps
>(function PriceChartPanel(
  { height, showVolume = true, showTimeScale = true, className = "" },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<PriceChartPanelImpl | null>(null);
  const [initialized, setInitialized] = useState(false);

  // Create panel instance and initialize when container is ready
  // NOTE: height is intentionally excluded from these deps (showTimeScale is
  // excluded too, see comment below). Height changes are handled by the
  // separate resize effect below, which calls .resize() on the existing
  // chart instance instead of destroying and recreating it. Do not "fix"
  // this by adding height to these deps (that's the panels/ pattern, e.g.
  // RSIPanel/MACDPanel) — doing so would reintroduce destroy/recreate
  // thrash on every height change.
  useEffect(() => {
    if (!containerRef.current) return;

    // Create new instance
    const panel = new PriceChartPanelImpl({ height }, showVolume);
    panelRef.current = panel;

    // Initialize with container, passing time scale visibility option
    panel.initialize(containerRef.current, {
      timeScale: {
        visible: showTimeScale,
      },
    });
    setInitialized(true);

    return () => {
      panel.cleanup();
      panelRef.current = null;
      setInitialized(false);
    };
  }, [showVolume]); // Don't include showTimeScale - use separate effect to update it

  // Update time scale visibility without recreating the chart
  useEffect(() => {
    if (panelRef.current && initialized) {
      panelRef.current.setTimeScaleVisible(showTimeScale);
    }
  }, [showTimeScale, initialized]);

  // Handle height changes via resize
  useEffect(() => {
    if (panelRef.current && containerRef.current && initialized) {
      panelRef.current.resize(containerRef.current.clientWidth, height);
    }
  }, [height, initialized]);

  useImperativeHandle(
    ref,
    () => ({
      initialize: (
        container: HTMLDivElement,
        options?: DeepPartial<ChartOptions>,
      ) => {
        panelRef.current?.initialize(container, options);
      },
      updateData: (data: PriceChartData) => {
        panelRef.current?.updateData(data);
      },
      setOnCrosshairMove: (callback: CrosshairMoveCallback) => {
        panelRef.current?.setOnCrosshairMove(callback);
      },
      setOnTimeRangeChange: (callback: TimeRangeChangeCallback) => {
        panelRef.current?.setOnTimeRangeChange(callback);
      },
      syncCrosshair: (data: CrosshairData) => {
        panelRef.current?.syncCrosshair(data);
      },
      syncTimeRange: (range: any) => {
        panelRef.current?.syncTimeRange(range);
      },
      resize: (width: number, height: number) => {
        panelRef.current?.resize(width, height);
      },
      fitContent: () => {
        panelRef.current?.fitContent();
      },
      cleanup: () => {
        panelRef.current?.cleanup();
      },
      getChart: () => panelRef.current?.getChart() ?? null,
      getLegendData: (time: Time) => {
        return (
          panelRef.current?.getLegendData(time) ?? {
            time: null,
            ohlc: null,
            volume: null,
            overlays: [],
          }
        );
      },
      setMarkers: (markers: SeriesMarker<Time>[]) => {
        panelRef.current?.setMarkers(markers);
      },
      addOverlay: (indicator: OverlayIndicatorData) => {
        panelRef.current?.addOverlay(indicator);
      },
      removeOverlay: (name: string) => {
        panelRef.current?.removeOverlay(name);
      },
      setCrosshairMode: (mode: CrosshairMode) => {
        panelRef.current?.setCrosshairMode(mode);
      },
      setHorzLineLabelVisible: (visible: boolean) => {
        panelRef.current?.setHorzLineLabelVisible(visible);
      },
      setTimeScaleVisible: (visible: boolean) => {
        panelRef.current?.setTimeScaleVisible(visible);
      },
    }),
    [initialized],
  );

  return (
    <div
      ref={containerRef}
      className={`price-chart-panel ${className}`}
      style={{ height: `${height}px`, width: "100%" }}
    />
  );
});

export default PriceChartPanel;
export { CrosshairMode };
