"use client";

/**
 * StochasticPanel - Specialized panel for Stochastic oscillator
 *
 * Features:
 * - %K line (main) and %D line (signal)
 * - Fixed scale: 0-100
 * - Threshold lines at 20 (oversold) and 80 (overbought)
 * - Shaded zone between 20-80
 */

import React, {
  forwardRef,
  useRef,
  useEffect,
  useImperativeHandle,
  useCallback,
} from "react";
import { LineSeries } from "lightweight-charts";
import type {
  Time,
  DeepPartial,
  ChartOptions,
  LineData,
  ISeriesApi,
} from "lightweight-charts";
import {
  BaseChartPanel,
  ChartPanelConfig,
  CrosshairData,
  CrosshairMoveCallback,
  TimeRangeChangeCallback,
} from "../charts/BaseChartPanel";

// Stochastic calculation
function calculateSMA(data: number[], period: number): number[] {
  const sma: number[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      sma.push(data[i]);
    } else {
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += data[i - j];
      }
      sma.push(sum / period);
    }
  }
  return sma;
}

function calculateStochastic(
  highs: number[],
  lows: number[],
  closes: number[],
  kPeriod: number = 14,
  dPeriod: number = 3,
  smooth: number = 3,
): { k: number[]; d: number[] } {
  const rawK: number[] = [];

  for (let i = 0; i < closes.length; i++) {
    if (i < kPeriod - 1) {
      rawK.push(50); // Default neutral value
    } else {
      let highestHigh = -Infinity;
      let lowestLow = Infinity;

      for (let j = 0; j < kPeriod; j++) {
        highestHigh = Math.max(highestHigh, highs[i - j]);
        lowestLow = Math.min(lowestLow, lows[i - j]);
      }

      const range = highestHigh - lowestLow;
      if (range === 0) {
        rawK.push(50);
      } else {
        rawK.push(((closes[i] - lowestLow) / range) * 100);
      }
    }
  }

  // Smooth %K
  const k = calculateSMA(rawK, smooth);

  // %D is SMA of %K
  const d = calculateSMA(k, dPeriod);

  return { k, d };
}

export interface StochasticPanelConfig {
  kPeriod: number;
  dPeriod: number;
  smooth: number;
  overbought: number;
  oversold: number;
}

export interface StochasticData {
  time: Time;
  k: number;
  d: number;
}

export interface StochasticLegendData {
  time: Time | null;
  indicatorName: string;
  k: number | null;
  d: number | null;
}

export interface StochasticPanelProps {
  height: number;
  config?: StochasticPanelConfig;
  showTimeScale?: boolean; // Whether to show time scale (for bottom-most panel)
  className?: string;
}

export interface StochasticPanelRef {
  initialize: (
    container: HTMLDivElement,
    options?: DeepPartial<ChartOptions>,
  ) => void;
  updateData: (data: StochasticData[]) => void;
  calculateAndUpdate: (
    candleData: { time: Time; high: number; low: number; close: number }[],
  ) => void;
  setOnCrosshairMove: (callback: CrosshairMoveCallback) => void;
  setOnTimeRangeChange: (callback: TimeRangeChangeCallback) => void;
  syncCrosshair: (data: CrosshairData) => void;
  syncTimeRange: (range: any) => void;
  resize: (width: number, height: number) => void;
  fitContent: () => void;
  cleanup: () => void;
  getChart: () => any;
  getLegendData: (time: Time) => StochasticLegendData;
  getPanelId: () => string;
  getIndicatorName: () => string;
  setHorzLineLabelVisible: (visible: boolean) => void;
}

const DEFAULT_CONFIG: StochasticPanelConfig = {
  kPeriod: 14,
  dPeriod: 3,
  smooth: 3,
  overbought: 80,
  oversold: 20,
};

const K_COLOR = "#22c55e"; // Green
const D_COLOR = "#ef4444"; // Red

class StochasticPanelImpl extends BaseChartPanel {
  private kSeries: ISeriesApi<"Line"> | null = null;
  private dSeries: ISeriesApi<"Line"> | null = null;
  private stochData: StochasticData[] = [];
  private panelConfig: StochasticPanelConfig;

  constructor(config: ChartPanelConfig, stochConfig: StochasticPanelConfig) {
    super("stoch", config);
    this.panelConfig = stochConfig;
  }

  protected onInitialize(): void {
    if (!this.chart) return;

    // Configure fixed 0-100 scale
    this.chart.priceScale("right").applyOptions({
      autoScale: false,
      borderColor: "rgba(255, 255, 255, 0.1)",
      visible: true,
      scaleMargins: { top: 0.1, bottom: 0.1 },
    });

    // Hide time scale
    this.chart.timeScale().applyOptions({
      visible: false,
    });

    // Add threshold lines
    const overboughtLine = this.chart.addSeries(LineSeries, {
      color: "rgba(255, 255, 255, 0.2)",
      lineWidth: 1 as 1 | 2 | 3 | 4,
      lineStyle: 2,
      priceScaleId: "right",
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });

    const oversoldLine = this.chart.addSeries(LineSeries, {
      color: "rgba(255, 255, 255, 0.2)",
      lineWidth: 1 as 1 | 2 | 3 | 4,
      lineStyle: 2,
      priceScaleId: "right",
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });

    // Create %K line
    this.kSeries = this.chart.addSeries(LineSeries, {
      color: K_COLOR,
      lineWidth: 2 as 1 | 2 | 3 | 4,
      priceScaleId: "right",
      lastValueVisible: true,
      priceLineVisible: false,
    });

    // Create %D line
    this.dSeries = this.chart.addSeries(LineSeries, {
      color: D_COLOR,
      lineWidth: 2 as 1 | 2 | 3 | 4,
      priceScaleId: "right",
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // Apply fixed scale
    this.kSeries.applyOptions({
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: 0, maxValue: 100 },
      }),
    });
  }

  getMainSeries(): ISeriesApi<"Line"> | null {
    return this.kSeries;
  }

  updateData(data: StochasticData[]): void {
    if (!this.chart || !this.kSeries || !this.dSeries) return;

    this.stochData = data;

    // Set %K data
    const kData: LineData<Time>[] = data.map((d) => ({
      time: d.time,
      value: d.k,
    }));
    this.kSeries.setData(kData);

    // Set %D data
    const dData: LineData<Time>[] = data.map((d) => ({
      time: d.time,
      value: d.d,
    }));
    this.dSeries.setData(dData);
  }

  getCrosshairValue(time: Time): StochasticData | null {
    return this.stochData.find((d) => d.time === time) ?? null;
  }

  getLegendData(time: Time): StochasticLegendData {
    const data = this.findDataAtTime(time);
    return {
      time,
      indicatorName: `Stoch(${this.panelConfig.kPeriod},${this.panelConfig.dPeriod},${this.panelConfig.smooth})`,
      k: data?.k ?? null,
      d: data?.d ?? null,
    };
  }

  private findDataAtTime(time: Time): StochasticData | null {
    const exactMatch = this.stochData.find((d) => d.time === time);
    if (exactMatch) return exactMatch;

    if (this.stochData.length === 0) return null;

    const timeNum =
      typeof time === "number"
        ? time
        : new Date(time as string).getTime() / 1000;

    let closest = this.stochData[0];
    let minDiff = Infinity;

    for (const dataPoint of this.stochData) {
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
    this.kSeries = null;
    this.dSeries = null;
    this.stochData = [];
    super.cleanup();
  }
}

export const StochasticPanel = forwardRef<
  StochasticPanelRef,
  StochasticPanelProps
>(function StochasticPanel(
  { height, config = DEFAULT_CONFIG, showTimeScale = false, className = "" },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<StochasticPanelImpl | null>(null);

  const indicatorName = `Stoch(${config.kPeriod},${config.dPeriod},${config.smooth})`;

  useEffect(() => {
    panelRef.current = new StochasticPanelImpl({ height }, config);
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
    (
      candleData: { time: Time; high: number; low: number; close: number }[],
    ) => {
      const highs = candleData.map((c) => c.high);
      const lows = candleData.map((c) => c.low);
      const closes = candleData.map((c) => c.close);
      const { k, d } = calculateStochastic(
        highs,
        lows,
        closes,
        config.kPeriod,
        config.dPeriod,
        config.smooth,
      );

      const panelData: StochasticData[] = candleData.map((c, i) => ({
        time: c.time,
        k: k[i] ?? 50,
        d: d[i] ?? 50,
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
      updateData: (data: StochasticData[]) => {
        panelRef.current?.updateData(data);
      },
      calculateAndUpdate,
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
      getLegendData: (time: Time): StochasticLegendData => {
        return (
          panelRef.current?.getLegendData(time) ?? {
            time: null,
            indicatorName,
            k: null,
            d: null,
          }
        );
      },
      getPanelId: () => panelRef.current?.getPanelId() ?? "stoch",
      getIndicatorName: () => indicatorName,
      setHorzLineLabelVisible: (visible: boolean) => {
        panelRef.current?.setHorzLineLabelVisible(visible);
      },
    }),
    [indicatorName, calculateAndUpdate],
  );

  useEffect(() => {
    if (containerRef.current && panelRef.current) {
      panelRef.current.initialize(containerRef.current);
    }
  }, []);

  return (
    <div className={`stochastic-panel relative ${className}`}>
      {/* Stochastic Label in top-left */}
      <div className="absolute top-2 left-2 z-10 flex items-center gap-3 text-xs">
        <span className="font-medium" style={{ color: K_COLOR }}>
          {indicatorName}
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-2 h-0.5"
            style={{ backgroundColor: K_COLOR }}
          ></span>
          <span style={{ color: K_COLOR }}>%K</span>
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block w-2 h-0.5"
            style={{ backgroundColor: D_COLOR }}
          ></span>
          <span style={{ color: D_COLOR }}>%D</span>
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
});

export default StochasticPanel;
