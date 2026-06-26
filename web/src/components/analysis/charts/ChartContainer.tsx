"use client";

/**
 * ChartContainer - Orchestrates multiple chart panels with synchronized crosshair and time axis
 *
 * This component manages:
 * - Price chart panel (main) with optional snap-to-price crosshair
 * - Indicator panels (RSI, MACD, Stochastic, etc.) with free-moving crosshair
 * - Crosshair synchronization across all panels
 * - Time axis synchronization (zoom/pan)
 * - Dynamic height allocation based on active panels
 */

import React, {
  useRef,
  useEffect,
  useState,
  useCallback,
  forwardRef,
  useImperativeHandle,
  useMemo,
} from "react";
import type { Time, SeriesMarker, LogicalRange } from "lightweight-charts";
import { CrosshairMode } from "lightweight-charts";
import {
  PriceChartPanel,
  PriceChartPanelRef,
  PriceChartData,
  PriceChartLegendData,
} from "./PriceChartPanel";
import type {
  CrosshairData,
  CrosshairMoveCallback,
  TimeRangeChangeCallback,
} from "./BaseChartPanel";
import { CrosshairSync } from "./sync/CrosshairSync";
import { TimeAxisSync } from "./sync/TimeAxisSync";
import { RSIPanel, RSIPanelRef, RSIPanelConfig } from "../panels/RSIPanel";
import {
  MACDPanel,
  MACDPanelRef,
  MACDLegendData,
  MACDPanelConfig,
} from "../panels/MACDPanel";
import {
  StochasticPanel,
  StochasticPanelRef,
  StochasticLegendData,
  StochasticPanelConfig,
} from "../panels/StochasticPanel";
import type { PanelLegendData } from "./PanelChartPanel";

// Types
export interface ActivePanel {
  type: "rsi" | "macd" | "stoch" | "adx" | "atr";
  // ADX/ATR don't have dedicated panel components or config types yet
  // (see ChartContainer's panel switch below, which falls through to null
  // for those types) - config is unused until those panels are implemented.
  // Record<string, number | string> covers the generic agent/UI-driven
  // indicator params shape (IndicatorConfig.params in AnalysisContext) -
  // callers building ActivePanel from live indicator state pass that
  // generic shape rather than one of the three typed config interfaces.
  config?:
    | RSIPanelConfig
    | MACDPanelConfig
    | StochasticPanelConfig
    | Record<string, number | string>;
}

export interface ChartContainerProps {
  height: number;
  width?: number;
  showVolume?: boolean;
  activePanels?: ActivePanel[];
  snapToPrice?: boolean;
  onCrosshairMove?: (data: CrosshairLegendData) => void;
  onSnapToPriceChange?: (snapToPrice: boolean) => void;
  className?: string;
}

export interface CrosshairLegendData {
  time: Time | null;
  priceData: PriceChartLegendData | null;
  panelData: Map<
    string,
    PanelLegendData | MACDLegendData | StochasticLegendData
  >;
  activePanel: string;
}

export interface ChartContainerRef {
  updatePriceData: (data: PriceChartData) => void;
  updateCandleData: (
    candleData: {
      time: Time;
      open: number;
      high: number;
      low: number;
      close: number;
    }[],
  ) => void;
  setMarkers: (markers: SeriesMarker<Time>[]) => void;
  fitContent: () => void;
  setTimeRange: (range: LogicalRange) => void;
  resize: (width: number, height: number) => void;
  getPriceChart: () => PriceChartPanelRef | null;
  getPanel: (
    type: string,
  ) => RSIPanelRef | MACDPanelRef | StochasticPanelRef | null;
  setSnapToPrice: (snap: boolean) => void;
}

// Height allocation based on number of panels
function calculateHeights(
  totalHeight: number,
  panelCount: number,
): { priceHeight: number; panelHeight: number } {
  if (panelCount === 0) {
    return { priceHeight: totalHeight, panelHeight: 0 };
  }

  if (panelCount === 1) {
    return {
      priceHeight: Math.floor(totalHeight * 0.7),
      panelHeight: Math.floor(totalHeight * 0.3),
    };
  }

  if (panelCount === 2) {
    return {
      priceHeight: Math.floor(totalHeight * 0.55),
      panelHeight: Math.floor(totalHeight * 0.225),
    };
  }

  // 3+ panels
  const priceHeight = Math.floor(totalHeight * 0.45);
  const remainingHeight = totalHeight - priceHeight;
  const panelHeight = Math.floor(remainingHeight / panelCount);
  return { priceHeight, panelHeight };
}

export const ChartContainer = forwardRef<
  ChartContainerRef,
  ChartContainerProps
>(function ChartContainer(
  {
    height,
    width,
    showVolume = true,
    activePanels = [],
    snapToPrice = false,
    onCrosshairMove,
    onSnapToPriceChange,
    className = "",
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Chart panel refs
  const priceChartRef = useRef<PriceChartPanelRef>(null);
  const rsiPanelRef = useRef<RSIPanelRef>(null);
  const macdPanelRef = useRef<MACDPanelRef>(null);
  const stochPanelRef = useRef<StochasticPanelRef>(null);

  // Synchronization managers
  const crosshairSyncRef = useRef<CrosshairSync | null>(null);
  const timeAxisSyncRef = useRef<TimeAxisSync | null>(null);

  // State
  const [candleData, setCandleData] = useState<
    { time: Time; open: number; high: number; low: number; close: number }[]
  >([]);
  const [activePanel, setActivePanel] = useState<string>("price");

  // Calculate heights
  const { priceHeight, panelHeight } = useMemo(() => {
    return calculateHeights(height, activePanels.length);
  }, [height, activePanels.length]);

  // Check which panels are active (for sync registration and data updates)
  const hasRSI = activePanels.some((p) => p.type === "rsi");
  const hasMACD = activePanels.some((p) => p.type === "macd");
  const hasStoch = activePanels.some((p) => p.type === "stoch");

  // Time scale only shows on bottom-most panel
  // Panels render in the order they appear in activePanels array
  const hasPanelsBelow = activePanels.length > 0;
  const priceShowTimeScale = !hasPanelsBelow;

  // Update price chart crosshair mode when snapToPrice changes
  useEffect(() => {
    if (priceChartRef.current) {
      const mode = snapToPrice ? CrosshairMode.Magnet : CrosshairMode.Normal;
      priceChartRef.current.setCrosshairMode(mode);
    }
  }, [snapToPrice]);

  // Handle crosshair move callback
  const handleCrosshairMove = useCallback(
    (data: CrosshairData, sourcePanel: string) => {
      setActivePanel(sourcePanel);

      // Toggle horizontal line label visibility based on active panel
      // Only the active panel shows its value on the right side
      priceChartRef.current?.setHorzLineLabelVisible(sourcePanel === "price");
      rsiPanelRef.current?.setHorzLineLabelVisible(sourcePanel === "rsi");
      macdPanelRef.current?.setHorzLineLabelVisible(sourcePanel === "macd");
      stochPanelRef.current?.setHorzLineLabelVisible(sourcePanel === "stoch");

      if (onCrosshairMove && data.time) {
        const legendData: CrosshairLegendData = {
          time: data.time,
          priceData: priceChartRef.current?.getLegendData(data.time) ?? null,
          panelData: new Map(),
          activePanel: sourcePanel,
        };

        if (hasRSI && rsiPanelRef.current) {
          legendData.panelData.set(
            "rsi",
            rsiPanelRef.current.getLegendData(data.time),
          );
        }
        if (hasMACD && macdPanelRef.current) {
          legendData.panelData.set(
            "macd",
            macdPanelRef.current.getLegendData(data.time),
          );
        }
        if (hasStoch && stochPanelRef.current) {
          legendData.panelData.set(
            "stoch",
            stochPanelRef.current.getLegendData(data.time),
          );
        }

        onCrosshairMove(legendData);
      }
    },
    [onCrosshairMove, hasRSI, hasMACD, hasStoch],
  );

  // Initialize sync managers
  useEffect(() => {
    crosshairSyncRef.current = new CrosshairSync();
    timeAxisSyncRef.current = new TimeAxisSync();

    return () => {
      crosshairSyncRef.current?.cleanup();
      timeAxisSyncRef.current?.cleanup();
    };
  }, []);

  // Register price chart with sync managers when it's ready
  useEffect(() => {
    if (
      !priceChartRef.current ||
      !crosshairSyncRef.current ||
      !timeAxisSyncRef.current
    )
      return;

    const priceChart = priceChartRef.current;
    const panelId = "price";

    // Create sync wrapper for price chart
    const priceSyncPanel = {
      getPanelId: () => panelId,
      syncCrosshair: (data: CrosshairData) => {
        priceChart.syncCrosshair(data);
      },
      clearCrosshair: () => priceChart.getChart()?.clearCrosshairPosition(),
      setOnCrosshairMove: (callback: CrosshairMoveCallback) =>
        priceChart.setOnCrosshairMove(callback),
    };

    const priceTimePanel = {
      getPanelId: () => panelId,
      syncTimeRange: (range: LogicalRange | null) => {
        priceChart.syncTimeRange(range);
      },
      getVisibleTimeRange: () =>
        priceChart.getChart()?.timeScale().getVisibleLogicalRange() ?? null,
      setOnTimeRangeChange: (callback: TimeRangeChangeCallback) =>
        priceChart.setOnTimeRangeChange(callback),
      fitContent: () => priceChart.fitContent(),
    };

    crosshairSyncRef.current.registerPanel(priceSyncPanel);
    timeAxisSyncRef.current.registerPanel(priceTimePanel);

    // Setup crosshair move handler to track active panel
    // Use syncCrosshairExcept to preserve free-moving crosshair on source panel
    priceChart.setOnCrosshairMove(
      (data: CrosshairData, sourcePanel: string) => {
        setActivePanel("price");
        handleCrosshairMove(data, "price");
        crosshairSyncRef.current?.syncCrosshairExcept(data, "price");
      },
    );

    // Setup time range change handler
    priceChart.setOnTimeRangeChange(
      (range: LogicalRange | null, sourcePanel: string) => {
        timeAxisSyncRef.current?.setTimeRange(range);
      },
    );
  }, [handleCrosshairMove]);

  // Register RSI panel with sync managers when it's ready
  useEffect(() => {
    if (
      !hasRSI ||
      !rsiPanelRef.current ||
      !crosshairSyncRef.current ||
      !timeAxisSyncRef.current
    ) {
      if (!hasRSI) {
        crosshairSyncRef.current?.unregisterPanel("rsi");
        timeAxisSyncRef.current?.unregisterPanel("rsi");
      }
      return;
    }

    const rsiPanel = rsiPanelRef.current;
    const panelId = "rsi";

    const rsiSyncPanel = {
      getPanelId: () => panelId,
      syncCrosshair: (data: CrosshairData) => {
        rsiPanel.syncCrosshair(data);
      },
      clearCrosshair: () => rsiPanel.getChart()?.clearCrosshairPosition(),
      setOnCrosshairMove: (callback: CrosshairMoveCallback) =>
        rsiPanel.setOnCrosshairMove(callback),
    };

    const rsiTimePanel = {
      getPanelId: () => panelId,
      syncTimeRange: (range: LogicalRange | null) => {
        rsiPanel.syncTimeRange(range);
      },
      getVisibleTimeRange: () =>
        rsiPanel.getChart()?.timeScale().getVisibleLogicalRange() ?? null,
      setOnTimeRangeChange: (callback: TimeRangeChangeCallback) =>
        rsiPanel.setOnTimeRangeChange(callback),
      fitContent: () => rsiPanel.fitContent(),
    };

    crosshairSyncRef.current.registerPanel(rsiSyncPanel);
    timeAxisSyncRef.current.registerPanel(rsiTimePanel);

    // Use syncCrosshairExcept to preserve free-moving crosshair on source panel
    rsiPanel.setOnCrosshairMove((data: CrosshairData, sourcePanel: string) => {
      setActivePanel("rsi");
      handleCrosshairMove(data, "rsi");
      crosshairSyncRef.current?.syncCrosshairExcept(data, "rsi");
    });

    rsiPanel.setOnTimeRangeChange(
      (range: LogicalRange | null, sourcePanel: string) => {
        timeAxisSyncRef.current?.setTimeRange(range);
      },
    );
  }, [hasRSI, handleCrosshairMove]);

  // Register MACD panel with sync managers when it's ready
  useEffect(() => {
    if (
      !hasMACD ||
      !macdPanelRef.current ||
      !crosshairSyncRef.current ||
      !timeAxisSyncRef.current
    ) {
      if (!hasMACD) {
        crosshairSyncRef.current?.unregisterPanel("macd");
        timeAxisSyncRef.current?.unregisterPanel("macd");
      }
      return;
    }

    const macdPanel = macdPanelRef.current;
    const panelId = "macd";

    const macdSyncPanel = {
      getPanelId: () => panelId,
      syncCrosshair: (data: CrosshairData) => {
        macdPanel.syncCrosshair(data);
      },
      clearCrosshair: () => macdPanel.getChart()?.clearCrosshairPosition(),
      setOnCrosshairMove: (callback: CrosshairMoveCallback) =>
        macdPanel.setOnCrosshairMove(callback),
    };

    const macdTimePanel = {
      getPanelId: () => panelId,
      syncTimeRange: (range: LogicalRange | null) => {
        macdPanel.syncTimeRange(range);
      },
      getVisibleTimeRange: () =>
        macdPanel.getChart()?.timeScale().getVisibleLogicalRange() ?? null,
      setOnTimeRangeChange: (callback: TimeRangeChangeCallback) =>
        macdPanel.setOnTimeRangeChange(callback),
      fitContent: () => macdPanel.fitContent(),
    };

    crosshairSyncRef.current.registerPanel(macdSyncPanel);
    timeAxisSyncRef.current.registerPanel(macdTimePanel);

    // Use syncCrosshairExcept to preserve free-moving crosshair on source panel
    macdPanel.setOnCrosshairMove((data: CrosshairData, sourcePanel: string) => {
      setActivePanel("macd");
      handleCrosshairMove(data, "macd");
      crosshairSyncRef.current?.syncCrosshairExcept(data, "macd");
    });

    macdPanel.setOnTimeRangeChange(
      (range: LogicalRange | null, sourcePanel: string) => {
        timeAxisSyncRef.current?.setTimeRange(range);
      },
    );
  }, [hasMACD, handleCrosshairMove]);

  // Register Stochastic panel with sync managers when it's ready
  useEffect(() => {
    if (
      !hasStoch ||
      !stochPanelRef.current ||
      !crosshairSyncRef.current ||
      !timeAxisSyncRef.current
    ) {
      if (!hasStoch) {
        crosshairSyncRef.current?.unregisterPanel("stoch");
        timeAxisSyncRef.current?.unregisterPanel("stoch");
      }
      return;
    }

    const stochPanel = stochPanelRef.current;
    const panelId = "stoch";

    const stochSyncPanel = {
      getPanelId: () => panelId,
      syncCrosshair: (data: CrosshairData) => {
        stochPanel.syncCrosshair(data);
      },
      clearCrosshair: () => stochPanel.getChart()?.clearCrosshairPosition(),
      setOnCrosshairMove: (callback: CrosshairMoveCallback) =>
        stochPanel.setOnCrosshairMove(callback),
    };

    const stochTimePanel = {
      getPanelId: () => panelId,
      syncTimeRange: (range: LogicalRange | null) => {
        stochPanel.syncTimeRange(range);
      },
      getVisibleTimeRange: () =>
        stochPanel.getChart()?.timeScale().getVisibleLogicalRange() ?? null,
      setOnTimeRangeChange: (callback: TimeRangeChangeCallback) =>
        stochPanel.setOnTimeRangeChange(callback),
      fitContent: () => stochPanel.fitContent(),
    };

    crosshairSyncRef.current.registerPanel(stochSyncPanel);
    timeAxisSyncRef.current.registerPanel(stochTimePanel);

    // Use syncCrosshairExcept to preserve free-moving crosshair on source panel
    stochPanel.setOnCrosshairMove(
      (data: CrosshairData, sourcePanel: string) => {
        setActivePanel("stoch");
        handleCrosshairMove(data, "stoch");
        crosshairSyncRef.current?.syncCrosshairExcept(data, "stoch");
      },
    );

    stochPanel.setOnTimeRangeChange(
      (range: LogicalRange | null, sourcePanel: string) => {
        timeAxisSyncRef.current?.setTimeRange(range);
      },
    );
  }, [hasStoch, handleCrosshairMove]);

  // Update indicator panels when candle data changes or panels are added/removed
  // Note: activePanels.length is included because adding a panel changes panelHeight,
  // which causes panel components to recreate their charts (empty). We need to
  // re-populate the data after the charts are recreated.
  useEffect(() => {
    if (candleData.length === 0) return;

    const updatePanels = () => {
      if (hasRSI && rsiPanelRef.current) {
        rsiPanelRef.current.calculateAndUpdate(candleData);
      }
      if (hasMACD && macdPanelRef.current) {
        macdPanelRef.current.calculateAndUpdate(candleData);
      }
      if (hasStoch && stochPanelRef.current) {
        stochPanelRef.current.calculateAndUpdate(candleData);
      }

      // After updating panel data, sync time range from price chart
      // This prevents the chart from shifting when panels are added
      if (priceChartRef.current) {
        const priceTimeRange = priceChartRef.current
          .getChart()
          ?.timeScale()
          .getVisibleLogicalRange();
        if (priceTimeRange && timeAxisSyncRef.current) {
          timeAxisSyncRef.current.setTimeRange(priceTimeRange);
        }
      }
    };

    updatePanels();
    const timeoutId = setTimeout(updatePanels, 100);

    return () => clearTimeout(timeoutId);
  }, [candleData, hasRSI, hasMACD, hasStoch, activePanels.length]);

  // Expose methods via ref
  useImperativeHandle(
    ref,
    () => ({
      updatePriceData: (data: PriceChartData) => {
        priceChartRef.current?.updateData(data);
        setCandleData(
          data.candles.map((c) => ({
            time: c.time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
          })),
        );
      },
      updateCandleData: (
        data: {
          time: Time;
          open: number;
          high: number;
          low: number;
          close: number;
        }[],
      ) => {
        setCandleData(data);
      },
      setMarkers: (markers: SeriesMarker<Time>[]) => {
        priceChartRef.current?.setMarkers(markers);
      },
      fitContent: () => {
        timeAxisSyncRef.current?.fitAllContent();
      },
      setTimeRange: (range: LogicalRange) => {
        timeAxisSyncRef.current?.setTimeRange(range);
      },
      resize: (w: number, h: number) => {
        const { priceHeight: ph, panelHeight: pah } = calculateHeights(
          h,
          activePanels.length,
        );
        priceChartRef.current?.resize(w, ph);
        if (hasRSI) rsiPanelRef.current?.resize(w, pah);
        if (hasMACD) macdPanelRef.current?.resize(w, pah);
        if (hasStoch) stochPanelRef.current?.resize(w, pah);
      },
      getPriceChart: () => priceChartRef.current,
      getPanel: (type: string) => {
        switch (type) {
          case "rsi":
            return rsiPanelRef.current;
          case "macd":
            return macdPanelRef.current;
          case "stoch":
            return stochPanelRef.current;
          default:
            return null;
        }
      },
      setSnapToPrice: (snap: boolean) => {
        if (priceChartRef.current) {
          const mode = snap ? CrosshairMode.Magnet : CrosshairMode.Normal;
          priceChartRef.current.setCrosshairMode(mode);
        }
        onSnapToPriceChange?.(snap);
      },
    }),
    [activePanels.length, hasRSI, hasMACD, hasStoch, onSnapToPriceChange],
  );

  return (
    <div
      ref={containerRef}
      className={`chart-container flex flex-col ${className}`}
      style={{ height: `${height}px`, width: width ? `${width}px` : "100%" }}
    >
      {/* Price Chart Panel */}
      <PriceChartPanel
        ref={priceChartRef}
        height={priceHeight}
        showVolume={showVolume}
        showTimeScale={priceShowTimeScale}
      />

      {/* Indicator Panels - rendered in the order they appear in activePanels array */}
      {activePanels.map((panel, index) => {
        const isLastPanel = index === activePanels.length - 1;
        const showTimeScale = isLastPanel;

        switch (panel.type) {
          case "rsi":
            return (
              <RSIPanel
                key="rsi"
                ref={rsiPanelRef}
                height={panelHeight}
                config={panel.config as RSIPanelConfig | undefined}
                showTimeScale={showTimeScale}
              />
            );
          case "macd":
            return (
              <MACDPanel
                key="macd"
                ref={macdPanelRef}
                height={panelHeight}
                config={panel.config as MACDPanelConfig | undefined}
                showTimeScale={showTimeScale}
              />
            );
          case "stoch":
            return (
              <StochasticPanel
                key="stoch"
                ref={stochPanelRef}
                height={panelHeight}
                config={panel.config as StochasticPanelConfig | undefined}
                showTimeScale={showTimeScale}
              />
            );
          default:
            return null;
        }
      })}
    </div>
  );
});
