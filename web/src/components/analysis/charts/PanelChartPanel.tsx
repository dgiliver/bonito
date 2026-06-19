"use client";

/**
 * PanelChartPanel - Base class for indicator panels (RSI, MACD, etc.)
 *
 * Each panel is its own Lightweight Charts instance with:
 * - Its own right-side scale showing indicator-appropriate values
 * - Synchronized time axis with the price chart
 * - Free-moving crosshair (always Normal mode, not Magnet)
 */

import React, {
  useRef,
  useEffect,
  useState,
  forwardRef,
  useImperativeHandle,
} from "react";
import { LineSeries, AreaSeries } from "lightweight-charts";
import type {
  ISeriesApi,
  Time,
  LineData,
  AreaData,
  DeepPartial,
  ChartOptions,
} from "lightweight-charts";
import {
  BaseChartPanel,
  ChartPanelConfig,
  CrosshairData,
  CrosshairMoveCallback,
  TimeRangeChangeCallback,
} from "./BaseChartPanel";

// Types
export interface PanelIndicatorData {
  time: Time;
  value: number;
}

export interface ThresholdLine {
  value: number;
  color: string;
  lineWidth?: number;
  lineStyle?: number;
}

export interface ThresholdZone {
  upper: number;
  lower: number;
  color: string;
}

export interface PanelChartConfig extends ChartPanelConfig {
  indicatorName: string;
  indicatorType: string;
  color: string;
  minValue?: number;
  maxValue?: number;
  thresholdLines?: ThresholdLine[];
  thresholdZone?: ThresholdZone;
  backgroundColor?: string;
  showTimeScale?: boolean; // Whether to show the time scale (dates) at bottom - only for bottom-most panel
}

export interface PanelLegendData {
  time: Time | null;
  indicatorName: string;
  value: number | null;
  color: string;
}

export interface PanelChartPanelRef {
  initialize: (
    container: HTMLDivElement,
    options?: DeepPartial<ChartOptions>,
  ) => void;
  updateData: (data: PanelIndicatorData[]) => void;
  setOnCrosshairMove: (callback: CrosshairMoveCallback) => void;
  setOnTimeRangeChange: (callback: TimeRangeChangeCallback) => void;
  syncCrosshair: (data: CrosshairData) => void;
  syncTimeRange: (range: any) => void;
  resize: (width: number, height: number) => void;
  fitContent: () => void;
  cleanup: () => void;
  getChart: () => any;
  getLegendData: (time: Time) => PanelLegendData;
  getPanelId: () => string;
  getIndicatorName: () => string;
  setHorzLineLabelVisible: (visible: boolean) => void;
}

// PanelChartPanelImpl - Class implementation
class PanelChartPanelImpl extends BaseChartPanel {
  private mainSeries: ISeriesApi<"Line"> | null = null;
  private thresholdSeries: ISeriesApi<"Line">[] = [];
  private zoneSeries: ISeriesApi<"Area">[] = [];
  private indicatorData: PanelIndicatorData[] = [];
  private panelConfig: PanelChartConfig;

  constructor(config: PanelChartConfig) {
    super(config.indicatorType, config);
    this.panelConfig = config;
  }

  protected onInitialize(): void {
    if (!this.chart) return;

    // Configure the price scale for this indicator
    // Note: autoScale must be TRUE for autoscaleInfoProvider to work
    // minimumWidth ensures alignment with price chart
    this.chart.priceScale("right").applyOptions({
      autoScale: true,
      borderColor: "rgba(0, 0, 0, 0.2)",
      visible: true,
      scaleMargins: { top: 0.05, bottom: 0.05 },
      minimumWidth: 60, // Match price chart for alignment
    });

    // Hide time scale on panel charts unless this is the bottom panel
    this.chart.timeScale().applyOptions({
      visible: this.panelConfig.showTimeScale ?? false,
    });

    // Create threshold zone if configured (e.g., RSI 30-70 zone)
    if (this.panelConfig.thresholdZone) {
      this.createThresholdZone(this.panelConfig.thresholdZone);
    }

    // Create threshold lines if configured
    if (this.panelConfig.thresholdLines) {
      for (const threshold of this.panelConfig.thresholdLines) {
        this.createThresholdLine(threshold);
      }
    }

    // Create main indicator line
    this.mainSeries = this.chart.addSeries(LineSeries, {
      color: this.panelConfig.color,
      lineWidth: 2 as 1 | 2 | 3 | 4,
      priceScaleId: "right",
      lastValueVisible: true,
      priceLineVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 5,
    });

    // Apply fixed scale if specified (e.g., RSI 0-100)
    if (
      this.panelConfig.minValue !== undefined &&
      this.panelConfig.maxValue !== undefined
    ) {
      const minVal = this.panelConfig.minValue;
      const maxVal = this.panelConfig.maxValue;

      // Use autoscaleInfoProvider to force the range
      this.mainSeries.applyOptions({
        autoscaleInfoProvider: () => ({
          priceRange: {
            minValue: minVal,
            maxValue: maxVal,
          },
        }),
      });

      // Configure the price scale with autoScale TRUE but constrained by autoscaleInfoProvider
      this.chart.priceScale("right").applyOptions({
        autoScale: true,
        scaleMargins: { top: 0.05, bottom: 0.05 },
      });
    }
  }

  private createThresholdZone(zone: ThresholdZone): void {
    if (!this.chart) return;

    // To create a band between lower (30) and upper (70):
    // 1. First area: fills from upper (70) down to 0 with zone color
    // 2. Second area: fills from lower (30) down to 0 with background color (mask)
    // The mask hides everything below 30, leaving only the 30-70 band visible

    // Area 1: Zone fill from upper (70) to bottom
    const zoneArea = this.chart.addSeries(AreaSeries, {
      lineColor: "transparent",
      topColor: zone.color,
      bottomColor: zone.color, // Solid color, not gradient
      lineWidth: 0 as 1 | 2 | 3 | 4,
      priceScaleId: "right",
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });

    // Area 2: Mask from lower (30) to bottom - covers zone below 30
    // Use the app's background color (warm cream from Bonito light theme)
    const maskColor = "#faf7f2"; // --bg-primary: warm cream
    const maskArea = this.chart.addSeries(AreaSeries, {
      lineColor: "transparent",
      topColor: maskColor,
      bottomColor: maskColor,
      lineWidth: 0 as 1 | 2 | 3 | 4,
      priceScaleId: "right",
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });

    // Apply scale constraints to both areas
    if (
      this.panelConfig.minValue !== undefined &&
      this.panelConfig.maxValue !== undefined
    ) {
      const minVal = this.panelConfig.minValue;
      const maxVal = this.panelConfig.maxValue;
      const scaleProvider = {
        autoscaleInfoProvider: () => ({
          priceRange: { minValue: minVal, maxValue: maxVal },
        }),
      };
      zoneArea.applyOptions(scaleProvider);
      maskArea.applyOptions(scaleProvider);
    }

    // Store both: zoneSeries[0] = zone fill, zoneSeries[1] = mask
    this.zoneSeries.push(zoneArea);
    this.zoneSeries.push(maskArea);
  }

  private createThresholdLine(threshold: ThresholdLine): void {
    if (!this.chart) return;

    const line = this.chart.addSeries(LineSeries, {
      color: threshold.color,
      lineWidth: (threshold.lineWidth ?? 1) as 1 | 2 | 3 | 4,
      lineStyle: threshold.lineStyle ?? 2, // Dashed by default
      priceScaleId: "right",
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });

    // Apply same scale constraints if min/max are set
    if (
      this.panelConfig.minValue !== undefined &&
      this.panelConfig.maxValue !== undefined
    ) {
      const minVal = this.panelConfig.minValue;
      const maxVal = this.panelConfig.maxValue;
      line.applyOptions({
        autoscaleInfoProvider: () => ({
          priceRange: { minValue: minVal, maxValue: maxVal },
        }),
      });
    }

    this.thresholdSeries.push(line);
  }

  getMainSeries(): ISeriesApi<"Line"> | null {
    return this.mainSeries;
  }

  getIndicatorName(): string {
    return this.panelConfig.indicatorName;
  }

  updateData(data: PanelIndicatorData[]): void {
    if (!this.chart || !this.mainSeries) return;

    this.indicatorData = data;

    const lineData: LineData<Time>[] = data.map((d) => ({
      time: d.time,
      value: d.value,
    }));

    this.mainSeries.setData(lineData);

    // DON'T call fitContent() here - let the time axis sync handle it
    // Calling fitContent would reset the view and cause chart shift issues

    // Update threshold lines with data points at same times
    if (this.panelConfig.thresholdLines) {
      this.panelConfig.thresholdLines.forEach((threshold, index) => {
        const series = this.thresholdSeries[index];
        if (series) {
          const thresholdData: LineData<Time>[] = data.map((d) => ({
            time: d.time,
            value: threshold.value,
          }));
          series.setData(thresholdData);
        }
      });
    }

    // Update threshold zone with data (two areas: zone fill + mask)
    if (this.panelConfig.thresholdZone && this.zoneSeries.length >= 2) {
      const zone = this.panelConfig.thresholdZone;

      // Zone area at upper (70) - fills down to bottom
      const zoneData: AreaData<Time>[] = data.map((d) => ({
        time: d.time,
        value: zone.upper,
      }));
      this.zoneSeries[0].setData(zoneData);

      // Mask area at lower (30) - covers zone below 30
      const maskData: AreaData<Time>[] = data.map((d) => ({
        time: d.time,
        value: zone.lower,
      }));
      this.zoneSeries[1].setData(maskData);
    }
  }

  getCrosshairValue(time: Time): number | null {
    const dataPoint = this.indicatorData.find((d) => d.time === time);
    return dataPoint?.value ?? null;
  }

  getLegendData(time: Time): PanelLegendData {
    const value = this.findValueAtTime(time);
    return {
      time,
      indicatorName: this.panelConfig.indicatorName,
      value,
      color: this.panelConfig.color,
    };
  }

  /**
   * Override base class method to return indicator value at time
   */
  protected getValueAtTime(time: Time): number | null {
    return this.findValueAtTime(time);
  }

  private findValueAtTime(time: Time): number | null {
    const exactMatch = this.indicatorData.find((d) => d.time === time);
    if (exactMatch) return exactMatch.value;

    if (this.indicatorData.length === 0) return null;

    // Find closest data point
    const timeNum =
      typeof time === "number"
        ? time
        : new Date(time as string).getTime() / 1000;

    let closest = this.indicatorData[0];
    let minDiff = Math.abs(
      (typeof closest.time === "number"
        ? closest.time
        : new Date(closest.time as string).getTime() / 1000) - timeNum,
    );

    for (const dataPoint of this.indicatorData) {
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

    return closest.value;
  }

  cleanup(): void {
    this.mainSeries = null;
    this.thresholdSeries = [];
    this.zoneSeries = [];
    this.indicatorData = [];
    super.cleanup();
  }
}

// React Component Wrapper
interface PanelChartPanelProps {
  config: PanelChartConfig;
  className?: string;
}

export const PanelChartPanel = forwardRef<
  PanelChartPanelRef,
  PanelChartPanelProps
>(function PanelChartPanel({ config, className = "" }, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<PanelChartPanelImpl | null>(null);
  const [initialized, setInitialized] = useState(false);

  // Store callbacks so they can be re-applied when impl is recreated
  const storedCrosshairCallbackRef = useRef<CrosshairMoveCallback | null>(null);
  const storedTimeRangeCallbackRef = useRef<TimeRangeChangeCallback | null>(
    null,
  );

  // Create and initialize panel when container is ready
  // NOTE: config.height is intentionally excluded from these deps. Height
  // changes are handled by the separate resize effect below, which calls
  // .resize() on the existing chart instance instead of destroying and
  // recreating it. Do not "fix" this by adding height/config here (that's
  // the panels/ pattern, e.g. RSIPanel/MACDPanel) — doing so would
  // reintroduce destroy/recreate thrash on every height change.
  useEffect(() => {
    if (!containerRef.current) return;

    const panel = new PanelChartPanelImpl(config);
    panelRef.current = panel;

    panel.initialize(containerRef.current, {
      layout: {
        background: { color: config.backgroundColor ?? "transparent" },
      },
    });

    // Re-apply stored callbacks to the new impl
    if (storedCrosshairCallbackRef.current) {
      panel.setOnCrosshairMove(storedCrosshairCallbackRef.current);
    }
    if (storedTimeRangeCallbackRef.current) {
      panel.setOnTimeRangeChange(storedTimeRangeCallbackRef.current);
    }

    setInitialized(true);

    return () => {
      panel.cleanup();
      panelRef.current = null;
      setInitialized(false);
    };
  }, [config.indicatorType, config.indicatorName]);

  // Handle height changes via resize
  useEffect(() => {
    if (panelRef.current && containerRef.current && initialized) {
      panelRef.current.resize(containerRef.current.clientWidth, config.height);
    }
  }, [config.height, initialized]);

  useImperativeHandle(
    ref,
    () => ({
      initialize: (
        container: HTMLDivElement,
        options?: DeepPartial<ChartOptions>,
      ) => {
        panelRef.current?.initialize(container, options);
      },
      updateData: (data: PanelIndicatorData[]) => {
        panelRef.current?.updateData(data);
      },
      setOnCrosshairMove: (callback: CrosshairMoveCallback) => {
        // Store callback so it survives impl recreation
        storedCrosshairCallbackRef.current = callback;
        panelRef.current?.setOnCrosshairMove(callback);
      },
      setOnTimeRangeChange: (callback: TimeRangeChangeCallback) => {
        storedTimeRangeCallbackRef.current = callback;
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
            indicatorName: config.indicatorName,
            value: null,
            color: config.color,
          }
        );
      },
      getPanelId: () => panelRef.current?.getPanelId() ?? config.indicatorType,
      getIndicatorName: () =>
        panelRef.current?.getIndicatorName() ?? config.indicatorName,
      setHorzLineLabelVisible: (visible: boolean) => {
        panelRef.current?.setHorzLineLabelVisible(visible);
      },
    }),
    [config, initialized],
  );

  return (
    <div
      ref={containerRef}
      className={`panel-chart-panel ${className}`}
      style={{
        height: `${config.height}px`,
        width: "100%",
        borderTop: "1px solid rgba(255, 255, 255, 0.1)",
      }}
    />
  );
});

export default PanelChartPanel;
