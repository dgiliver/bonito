"use client";

/**
 * MACDPanel - Specialized panel for MACD indicator
 *
 * Features:
 * - MACD line (blue)
 * - Signal line (red/orange)
 * - Histogram (green/red based on direction)
 * - Auto-scaled based on data range
 */

import React, {
  forwardRef,
  useRef,
  useEffect,
  useImperativeHandle,
  useCallback,
  useState,
} from "react";
import { LineSeries, HistogramSeries } from "lightweight-charts";
import type {
  Time,
  DeepPartial,
  ChartOptions,
  LineData,
  HistogramData,
  ISeriesApi,
} from "lightweight-charts";
import {
  BaseChartPanel,
  ChartPanelConfig,
  CrosshairData,
  CrosshairMoveCallback,
  TimeRangeChangeCallback,
} from "../charts/BaseChartPanel";

// MACD calculation
function calculateEMA(data: number[], period: number): number[] {
  const ema: number[] = [];
  const multiplier = 2 / (period + 1);

  if (data.length === 0) return [];

  // First EMA is simple average of first 'period' values
  let sum = 0;
  for (let i = 0; i < Math.min(period, data.length); i++) {
    sum += data[i];
  }
  ema.push(sum / Math.min(period, data.length));

  // Calculate subsequent EMAs
  for (let i = 1; i < data.length; i++) {
    if (i < period) {
      // Still in warmup period - use SMA
      let warmupSum = 0;
      for (let j = 0; j <= i; j++) {
        warmupSum += data[j];
      }
      ema.push(warmupSum / (i + 1));
    } else {
      ema.push(
        (data[i] - ema[ema.length - 1]) * multiplier + ema[ema.length - 1],
      );
    }
  }

  return ema;
}

function calculateMACD(
  closes: number[],
  fastPeriod: number = 12,
  slowPeriod: number = 26,
  signalPeriod: number = 9,
): { macd: number[]; signal: number[]; histogram: number[] } {
  const fastEMA = calculateEMA(closes, fastPeriod);
  const slowEMA = calculateEMA(closes, slowPeriod);

  // MACD line = Fast EMA - Slow EMA
  const macd: number[] = fastEMA.map((fast, i) => fast - slowEMA[i]);

  // Signal line = EMA of MACD line
  const signal = calculateEMA(macd, signalPeriod);

  // Histogram = MACD - Signal
  const histogram: number[] = macd.map((m, i) => m - signal[i]);

  return { macd, signal, histogram };
}

export interface MACDPanelConfig {
  fastPeriod: number;
  slowPeriod: number;
  signalPeriod: number;
}

export interface MACDData {
  time: Time;
  macd: number;
  signal: number;
  histogram: number;
}

export interface MACDLegendData {
  time: Time | null;
  indicatorName: string;
  macd: number | null;
  signal: number | null;
  histogram: number | null;
}

export interface MACDPanelProps {
  height: number;
  config?: MACDPanelConfig;
  showTimeScale?: boolean; // Whether to show time scale (for bottom-most panel)
  className?: string;
}

export interface MACDPanelRef {
  initialize: (
    container: HTMLDivElement,
    options?: DeepPartial<ChartOptions>,
  ) => void;
  updateData: (data: MACDData[]) => void;
  calculateAndUpdate: (candleData: { time: Time; close: number }[]) => void;
  setOnCrosshairMove: (callback: CrosshairMoveCallback) => void;
  setOnTimeRangeChange: (callback: TimeRangeChangeCallback) => void;
  syncCrosshair: (data: CrosshairData) => void;
  syncTimeRange: (range: any) => void;
  resize: (width: number, height: number) => void;
  fitContent: () => void;
  cleanup: () => void;
  getChart: () => any;
  getLegendData: (time: Time) => MACDLegendData;
  getPanelId: () => string;
  getIndicatorName: () => string;
  setHorzLineLabelVisible: (visible: boolean) => void;
}

const DEFAULT_CONFIG: MACDPanelConfig = {
  fastPeriod: 12,
  slowPeriod: 26,
  signalPeriod: 9,
};

const MACD_COLOR = "#3b82f6"; // Blue
const SIGNAL_COLOR = "#f97316"; // Orange
const HISTOGRAM_UP_COLOR = "rgba(34, 197, 94, 0.7)";
const HISTOGRAM_DOWN_COLOR = "rgba(239, 68, 68, 0.7)";

class MACDPanelImpl extends BaseChartPanel {
  private macdSeries: ISeriesApi<"Line"> | null = null;
  private signalSeries: ISeriesApi<"Line"> | null = null;
  private histogramSeries: ISeriesApi<"Histogram"> | null = null;
  private macdData: MACDData[] = [];
  private panelConfig: MACDPanelConfig;

  constructor(config: ChartPanelConfig, macdConfig: MACDPanelConfig) {
    super("macd", config);
    this.panelConfig = macdConfig;
  }

  protected onInitialize(): void {
    if (!this.chart) return;

    // Configure auto-scaling price scale
    this.chart.priceScale("right").applyOptions({
      autoScale: true,
      borderColor: "rgba(255, 255, 255, 0.1)",
      visible: true,
    });

    // Hide time scale (synced with price chart)
    this.chart.timeScale().applyOptions({
      visible: false,
    });

    // Create histogram series first (behind lines)
    this.histogramSeries = this.chart.addSeries(HistogramSeries, {
      color: HISTOGRAM_UP_COLOR,
      priceScaleId: "right",
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // Create MACD line
    this.macdSeries = this.chart.addSeries(LineSeries, {
      color: MACD_COLOR,
      lineWidth: 2 as 1 | 2 | 3 | 4,
      priceScaleId: "right",
      lastValueVisible: true,
      priceLineVisible: false,
    });

    // Create Signal line
    this.signalSeries = this.chart.addSeries(LineSeries, {
      color: SIGNAL_COLOR,
      lineWidth: 2 as 1 | 2 | 3 | 4,
      priceScaleId: "right",
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // Add zero line
    const zeroLine = this.chart.addSeries(LineSeries, {
      color: "rgba(255, 255, 255, 0.2)",
      lineWidth: 1 as 1 | 2 | 3 | 4,
      lineStyle: 2, // Dashed
      priceScaleId: "right",
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });
  }

  getMainSeries(): ISeriesApi<"Line"> | null {
    return this.macdSeries;
  }

  updateData(data: MACDData[]): void {
    if (
      !this.chart ||
      !this.macdSeries ||
      !this.signalSeries ||
      !this.histogramSeries
    )
      return;

    this.macdData = data;

    // Set MACD line data
    const macdLineData: LineData<Time>[] = data.map((d) => ({
      time: d.time,
      value: d.macd,
    }));
    this.macdSeries.setData(macdLineData);

    // Set Signal line data
    const signalLineData: LineData<Time>[] = data.map((d) => ({
      time: d.time,
      value: d.signal,
    }));
    this.signalSeries.setData(signalLineData);

    // Set Histogram data with colors based on direction
    const histogramData: HistogramData<Time>[] = data.map((d) => ({
      time: d.time,
      value: d.histogram,
      color: d.histogram >= 0 ? HISTOGRAM_UP_COLOR : HISTOGRAM_DOWN_COLOR,
    }));
    this.histogramSeries.setData(histogramData);
  }

  getCrosshairValue(time: Time): MACDData | null {
    return this.macdData.find((d) => d.time === time) ?? null;
  }

  getLegendData(time: Time): MACDLegendData {
    const data = this.findDataAtTime(time);
    return {
      time,
      indicatorName: `MACD(${this.panelConfig.fastPeriod},${this.panelConfig.slowPeriod},${this.panelConfig.signalPeriod})`,
      macd: data?.macd ?? null,
      signal: data?.signal ?? null,
      histogram: data?.histogram ?? null,
    };
  }

  private findDataAtTime(time: Time): MACDData | null {
    const exactMatch = this.macdData.find((d) => d.time === time);
    if (exactMatch) return exactMatch;

    if (this.macdData.length === 0) return null;

    const timeNum =
      typeof time === "number"
        ? time
        : new Date(time as string).getTime() / 1000;

    let closest = this.macdData[0];
    let minDiff = Infinity;

    for (const dataPoint of this.macdData) {
      const dataTimeNum =
        typeof dataPoint.time === "number"
          ? dataPoint.time
          : new Date(dataPoint.time as string).getTime() / 1000;
      const diff = Math.abs(dataTimeNum - timeNum);
      if (diff < minDiff) {
        minDiff = diff;
        closest = dataPoint;
      }
    }

    return closest;
  }

  cleanup(): void {
    this.macdSeries = null;
    this.signalSeries = null;
    this.histogramSeries = null;
    this.macdData = [];
    super.cleanup();
  }
}

export const MACDPanel = forwardRef<MACDPanelRef, MACDPanelProps>(
  function MACDPanel(
    { height, config = DEFAULT_CONFIG, showTimeScale = false, className = "" },
    ref,
  ) {
    const containerRef = useRef<HTMLDivElement>(null);
    const panelRef = useRef<MACDPanelImpl | null>(null);

    // State to track current MACD values - prevents data loss on crosshair events
    // Note: currentValues is used to preserve state during re-renders, not displayed in UI
    const [_currentValues, setCurrentValues] = useState<{
      macd: number | null;
      signal: number | null;
      histogram: number | null;
    }>({ macd: null, signal: null, histogram: null });

    const indicatorName = `MACD(${config.fastPeriod},${config.slowPeriod},${config.signalPeriod})`;

    useEffect(() => {
      panelRef.current = new MACDPanelImpl({ height }, config);
      return () => {
        panelRef.current?.cleanup();
        panelRef.current = null;
      };
    }, [height, config]);

    // Set time scale visibility after initialization
    useEffect(() => {
      if (containerRef.current && panelRef.current) {
        panelRef.current.setTimeScaleVisible(showTimeScale);
      }
    }, [showTimeScale]);

    const calculateAndUpdate = useCallback(
      (candleData: { time: Time; close: number }[]) => {
        const closes = candleData.map((c) => c.close);
        const { macd, signal, histogram } = calculateMACD(
          closes,
          config.fastPeriod,
          config.slowPeriod,
          config.signalPeriod,
        );

        const panelData: MACDData[] = candleData.map((c, i) => ({
          time: c.time,
          macd: macd[i] ?? 0,
          signal: signal[i] ?? 0,
          histogram: histogram[i] ?? 0,
        }));

        panelRef.current?.updateData(panelData);
      },
      [config],
    );

    useImperativeHandle(
      ref,
      () => ({
        initialize: (
          container: HTMLDivElement,
          options?: DeepPartial<ChartOptions>,
        ) => {
          panelRef.current?.initialize(container, options);
        },
        updateData: (data: MACDData[]) => {
          panelRef.current?.updateData(data);
        },
        calculateAndUpdate,
        setOnCrosshairMove: (callback: CrosshairMoveCallback) => {
          // Wrap callback to also update local value display (like RSIPanel)
          const wrappedCallback: CrosshairMoveCallback = (data, panelId) => {
            if (data.time && panelRef.current) {
              const legendData = panelRef.current.getLegendData(data.time);
              setCurrentValues({
                macd: legendData.macd,
                signal: legendData.signal,
                histogram: legendData.histogram,
              });
            } else {
              setCurrentValues({ macd: null, signal: null, histogram: null });
            }
            callback(data, panelId);
          };
          panelRef.current?.setOnCrosshairMove(wrappedCallback);
        },
        setOnTimeRangeChange: (callback: TimeRangeChangeCallback) => {
          panelRef.current?.setOnTimeRangeChange(callback);
        },
        syncCrosshair: (data: CrosshairData) => {
          panelRef.current?.syncCrosshair(data);
          // Update local MACD value display when crosshair syncs from another panel
          if (data.time && panelRef.current) {
            const legendData = panelRef.current.getLegendData(data.time);
            setCurrentValues({
              macd: legendData.macd,
              signal: legendData.signal,
              histogram: legendData.histogram,
            });
          } else {
            setCurrentValues({ macd: null, signal: null, histogram: null });
          }
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
        getLegendData: (time: Time): MACDLegendData => {
          return (
            panelRef.current?.getLegendData(time) ?? {
              time: null,
              indicatorName,
              macd: null,
              signal: null,
              histogram: null,
            }
          );
        },
        getPanelId: () => panelRef.current?.getPanelId() ?? "macd",
        getIndicatorName: () => indicatorName,
        setHorzLineLabelVisible: (visible: boolean) => {
          panelRef.current?.setHorzLineLabelVisible(visible);
        },
      }),
      [indicatorName, calculateAndUpdate],
    );

    // Initialize chart when container is ready or when panel impl is recreated
    // Note: We use height as a proxy for detecting when panelRef.current changes
    // because the useEffect at line 326 recreates panelRef.current when height changes
    useEffect(() => {
      if (containerRef.current && panelRef.current) {
        panelRef.current.initialize(containerRef.current);
      }
    }, [height, config]);

    return (
      <div className={`macd-panel relative ${className}`}>
        {/* MACD Label in top-left */}
        <div className="absolute top-2 left-2 z-10 flex items-center gap-3 text-xs">
          <span style={{ color: MACD_COLOR }}>{indicatorName}</span>
          <span className="flex items-center gap-1">
            <span
              className="inline-block w-2 h-0.5"
              style={{ backgroundColor: MACD_COLOR }}
            ></span>
            <span style={{ color: MACD_COLOR }}>MACD</span>
          </span>
          <span className="flex items-center gap-1">
            <span
              className="inline-block w-2 h-0.5"
              style={{ backgroundColor: SIGNAL_COLOR }}
            ></span>
            <span style={{ color: SIGNAL_COLOR }}>Signal</span>
          </span>
        </div>
        <div
          ref={containerRef}
          style={{
            height: `${height}px`,
            width: "100%",
            borderTop: "1px solid rgba(255, 255, 255, 0.1)",
          }}
        />
      </div>
    );
  },
);

export default MACDPanel;
