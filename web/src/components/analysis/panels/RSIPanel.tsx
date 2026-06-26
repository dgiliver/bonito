"use client";

/**
 * RSIPanel - Specialized panel for Relative Strength Index indicator
 *
 * Features:
 * - Fixed scale: 0-100
 * - Configurable threshold lines for overbought/oversold (default 30/70)
 * - Shaded zone between thresholds
 * - Purple color scheme
 * - Free-moving crosshair (always)
 */

import React, {
  forwardRef,
  useRef,
  useImperativeHandle,
  useCallback,
  useState,
} from "react";
import type { Time, DeepPartial, ChartOptions } from "lightweight-charts";
import {
  PanelChartPanel,
  PanelChartConfig,
  PanelIndicatorData,
  PanelChartPanelRef,
  PanelLegendData,
} from "../charts/PanelChartPanel";
import type {
  CrosshairData,
  CrosshairMoveCallback,
  TimeRangeChangeCallback,
} from "../charts/BaseChartPanel";

// RSI calculation function
function calculateRSI(closes: number[], period: number = 14): number[] {
  const rsi: number[] = [];

  if (closes.length < period + 1) {
    return closes.map(() => 50); // Default to neutral
  }

  // Calculate price changes
  const changes: number[] = [];
  for (let i = 1; i < closes.length; i++) {
    changes.push(closes[i] - closes[i - 1]);
  }

  // Calculate initial average gain and loss
  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 0; i < period; i++) {
    if (changes[i] > 0) {
      avgGain += changes[i];
    } else {
      avgLoss += Math.abs(changes[i]);
    }
  }

  avgGain /= period;
  avgLoss /= period;

  // Fill initial values with neutral RSI
  for (let i = 0; i < period; i++) {
    rsi.push(50);
  }

  // Calculate RSI for each subsequent period
  for (let i = period; i < changes.length; i++) {
    const change = changes[i];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? Math.abs(change) : 0;

    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;

    if (avgLoss === 0) {
      rsi.push(100);
    } else {
      const rs = avgGain / avgLoss;
      rsi.push(100 - 100 / (1 + rs));
    }
  }

  // The first value is for the close before changes
  rsi.unshift(50);

  return rsi;
}

export interface RSIPanelConfig {
  period: number;
  overbought: number;
  oversold: number;
}

export interface RSIPanelProps {
  height: number;
  config?: RSIPanelConfig;
  showTimeScale?: boolean; // Whether to show time scale (for bottom-most panel)
  className?: string;
}

export interface RSIPanelRef extends PanelChartPanelRef {
  calculateAndUpdate: (candleData: { time: Time; close: number }[]) => void;
  setHorzLineLabelVisible: (visible: boolean) => void;
}

const DEFAULT_CONFIG: RSIPanelConfig = {
  period: 14,
  overbought: 70,
  oversold: 30,
};

const RSI_COLOR = "#8b5cf6"; // Purple

export const RSIPanel = forwardRef<RSIPanelRef, RSIPanelProps>(
  function RSIPanel(
    { height, config, showTimeScale = false, className = "" },
    ref,
  ) {
    const panelRef = useRef<PanelChartPanelRef>(null);
    const [currentValue, setCurrentValue] = useState<number | null>(null);

    // Merge passed config with defaults to ensure overbought/oversold are always defined
    const mergedConfig = { ...DEFAULT_CONFIG, ...config };

    const panelConfig: PanelChartConfig = {
      height,
      indicatorName: `RSI(${mergedConfig.period})`,
      indicatorType: "rsi",
      color: RSI_COLOR,
      minValue: 0,
      maxValue: 100,
      thresholdLines: [
        {
          value: mergedConfig.overbought,
          color: "rgba(139, 92, 246, 0.7)",
          lineWidth: 1,
        },
        {
          value: mergedConfig.oversold,
          color: "rgba(139, 92, 246, 0.7)",
          lineWidth: 1,
        },
      ],
      thresholdZone: {
        upper: mergedConfig.overbought,
        lower: mergedConfig.oversold,
        color: "rgba(139, 92, 246, 0.25)", // Visible gradient from 70 line downward
      },
      backgroundColor: "rgba(139, 92, 246, 0.02)",
      showTimeScale, // Show time scale on bottom-most panel
    };

    const calculateAndUpdate = useCallback(
      (candleData: { time: Time; close: number }[]) => {
        const closes = candleData.map((c) => c.close);
        const rsiValues = calculateRSI(closes, mergedConfig.period);

        const panelData: PanelIndicatorData[] = candleData.map((c, i) => ({
          time: c.time,
          value: rsiValues[i] ?? 50,
        }));

        if (panelRef.current) {
          panelRef.current.updateData(panelData);
        }
      },
      [mergedConfig.period],
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
        updateData: (data: PanelIndicatorData[]) => {
          panelRef.current?.updateData(data);
        },
        setOnCrosshairMove: (callback: CrosshairMoveCallback) => {
          // Wrap callback to also update local value display
          const wrappedCallback: CrosshairMoveCallback = (data, panelId) => {
            if (data.time && panelRef.current) {
              const legendData = panelRef.current.getLegendData(data.time);
              setCurrentValue(legendData.value);
            } else {
              setCurrentValue(null);
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
          // Update local RSI value display when crosshair syncs from another panel
          if (data.time && panelRef.current) {
            const legendData = panelRef.current.getLegendData(data.time);
            setCurrentValue(legendData.value);
          } else {
            setCurrentValue(null);
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
        getLegendData: (time: Time): PanelLegendData => {
          return (
            panelRef.current?.getLegendData(time) ?? {
              time: null,
              indicatorName: panelConfig.indicatorName,
              value: null,
              color: RSI_COLOR,
            }
          );
        },
        getPanelId: () => panelRef.current?.getPanelId() ?? "rsi",
        getIndicatorName: () =>
          panelRef.current?.getIndicatorName() ?? panelConfig.indicatorName,
        calculateAndUpdate,
        setHorzLineLabelVisible: (visible: boolean) => {
          panelRef.current?.setHorzLineLabelVisible(visible);
        },
      }),
      [panelConfig.indicatorName, calculateAndUpdate],
    );

    return (
      <div
        className={`rsi-panel relative ${className}`}
        style={{ height: `${height}px` }}
      >
        {/* RSI Label in top-left with current value */}
        <div
          className="absolute top-2 left-2 z-10 text-xs font-medium flex items-center gap-2"
          style={{ color: RSI_COLOR }}
        >
          <span>{panelConfig.indicatorName}</span>
          {currentValue !== null && (
            <span className="font-mono">{currentValue.toFixed(2)}</span>
          )}
        </div>
        <PanelChartPanel ref={panelRef} config={panelConfig} />
      </div>
    );
  },
);
