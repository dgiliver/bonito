/**
 * BaseChartPanel - Abstract base class for all chart panels
 *
 * Each chart panel is its own Lightweight Charts instance with:
 * - Its own right-side scale showing appropriate values
 * - Synchronized time axis across all charts
 * - Synchronized crosshair position
 * - Independent auto-scaling
 */

import type {
  IChartApi,
  ISeriesApi,
  SeriesType,
  Time,
  MouseEventParams,
  LogicalRange,
  DeepPartial,
  ChartOptions,
} from "lightweight-charts";
import { createChart, CrosshairMode } from "lightweight-charts";

export interface ChartPanelConfig {
  height: number; // Height in pixels or percentage
  minHeight?: number;
  maxHeight?: number;
}

export interface CrosshairData {
  time: Time | null;
  price: number | null;
  logicalIndex: number | null;
}

export type CrosshairMoveCallback = (
  data: CrosshairData,
  sourcePanel: string,
) => void;
export type TimeRangeChangeCallback = (
  range: LogicalRange | null,
  sourcePanel: string,
) => void;

/**
 * Minimal structural shape of a lightweight-charts series data point as seen
 * from `MouseEventParams.seriesData` - candlestick/area points expose
 * `close`, line/histogram points expose `value`.
 */
interface SeriesDataPoint {
  close?: number;
  value?: number;
}

/**
 * BaseChartPanel is generic over each subclass's actual data/value/legend
 * shapes so abstract method signatures can be precisely typed instead of
 * `any`, without forcing every panel into a shared shape they don't use:
 * - TData: the parameter shape `updateData` accepts (e.g. PanelIndicatorData[])
 * - TCrosshairValue: the return shape of `getCrosshairValue`
 * - TLegendData: the return shape of `getLegendData` (must include `time`)
 */
export abstract class BaseChartPanel<
  TData = unknown,
  TCrosshairValue = unknown,
  TLegendData extends { time: Time | null } = { time: Time | null },
> {
  protected chart: IChartApi | null = null;
  protected container: HTMLDivElement | null = null;
  protected panelId: string;
  protected config: ChartPanelConfig;

  // Callbacks for synchronization
  protected onCrosshairMove: CrosshairMoveCallback | null = null;
  protected onTimeRangeChange: TimeRangeChangeCallback | null = null;

  // Flag to prevent infinite sync loops
  protected isSyncingCrosshair = false;
  protected isSyncingTimeRange = false;

  constructor(panelId: string, config: ChartPanelConfig) {
    this.panelId = panelId;
    this.config = config;
  }

  /**
   * Initialize the chart in the given container
   */
  initialize(
    container: HTMLDivElement,
    chartOptions?: DeepPartial<ChartOptions>,
  ): void {
    this.container = container;

    const defaultOptions: DeepPartial<ChartOptions> = {
      layout: {
        background: { color: "transparent" },
        textColor: "var(--text-secondary)",
        fontFamily: "var(--font-mono)",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.05)" },
        horzLines: { color: "rgba(255, 255, 255, 0.05)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal, // Free moving by default
        vertLine: {
          color: "rgba(0, 0, 0, 0.6)",
          width: 1,
          style: 2, // LineStyle.Dashed
          labelVisible: true,
          visible: true,
        },
        horzLine: {
          color: "rgba(0, 0, 0, 0.6)",
          width: 1,
          style: 2,
          labelVisible: true,
          visible: true,
        },
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
        visible: true,
        autoScale: true,
        minimumWidth: 60, // Fixed minimum width for alignment across panels
      },
      leftPriceScale: {
        visible: false,
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    };

    // Merge default options with provided options
    const mergedOptions = { ...defaultOptions, ...chartOptions };

    this.chart = createChart(container, mergedOptions);

    // Setup synchronization listeners
    this.setupSyncListeners();

    // Call subclass-specific initialization
    this.onInitialize();
  }

  /**
   * Setup listeners for crosshair and time range synchronization
   */
  protected setupSyncListeners(): void {
    if (!this.chart) return;

    // Crosshair move listener
    this.chart.subscribeCrosshairMove((param: MouseEventParams<Time>) => {
      if (this.isSyncingCrosshair) return;

      const crosshairData: CrosshairData = {
        time: param.time || null,
        price: null,
        logicalIndex: param.logical || null,
      };

      // Get price from the first series (if available)
      if (param.seriesData && param.seriesData.size > 0) {
        const firstSeries = param.seriesData.entries().next().value;
        if (firstSeries && firstSeries[1]) {
          const data = firstSeries[1] as SeriesDataPoint;
          crosshairData.price = data.close ?? data.value ?? null;
        }
      }

      if (this.onCrosshairMove) {
        this.onCrosshairMove(crosshairData, this.panelId);
      }
    });

    // Time range change listener
    this.chart
      .timeScale()
      .subscribeVisibleLogicalRangeChange((range: LogicalRange | null) => {
        if (this.isSyncingTimeRange) return;

        if (this.onTimeRangeChange) {
          this.onTimeRangeChange(range, this.panelId);
        }
      });
  }

  /**
   * Set callback for crosshair move events (for synchronization)
   */
  setOnCrosshairMove(callback: CrosshairMoveCallback): void {
    this.onCrosshairMove = callback;
  }

  /**
   * Set callback for time range change events (for synchronization)
   */
  setOnTimeRangeChange(callback: TimeRangeChangeCallback): void {
    this.onTimeRangeChange = callback;
  }

  /**
   * Set crosshair mode (Normal = free moving, Magnet = snap to price)
   */
  setCrosshairMode(mode: CrosshairMode): void {
    if (!this.chart) return;
    this.chart.applyOptions({
      crosshair: { mode },
    });
  }

  /**
   * Get current crosshair mode
   */
  getCrosshairMode(): CrosshairMode {
    if (!this.chart) return CrosshairMode.Normal;
    return this.chart.options().crosshair?.mode ?? CrosshairMode.Normal;
  }

  /**
   * Set time scale (dates at bottom) visibility
   * Used to show dates only on the bottom-most panel
   */
  setTimeScaleVisible(visible: boolean): void {
    if (!this.chart) return;
    this.chart.timeScale().applyOptions({
      visible,
    });
  }

  /**
   * Set horizontal line label visibility (the value shown on the right side of the chart)
   * Used to hide the label when this panel is not the active panel
   */
  setHorzLineLabelVisible(visible: boolean): void {
    if (!this.chart) return;
    this.chart.applyOptions({
      crosshair: {
        horzLine: {
          labelVisible: visible,
        },
      },
    });
  }

  /**
   * Sync crosshair position from another panel
   * Note: Each panel finds its OWN value at the synced time - don't use source panel's price
   */
  syncCrosshair(data: CrosshairData): void {
    if (!this.chart || !data.time) return;

    this.isSyncingCrosshair = true;
    try {
      // Get the main series for this panel
      const series = this.getMainSeries();
      if (series) {
        try {
          // Find this panel's value at the given time (not the source panel's price!)
          const localValue = this.getValueAtTime(data.time);

          if (localValue !== null) {
            this.chart.setCrosshairPosition(localValue, data.time, series);
          }
        } catch {
          // Series may not have data yet, ignore
        }
      }
    } finally {
      // Use setTimeout to reset flag after the event loop
      setTimeout(() => {
        this.isSyncingCrosshair = false;
      }, 0);
    }
  }

  /**
   * Get the value at a specific time for this panel's data
   * Override in subclasses for indicator-specific data lookup
   */
  protected getValueAtTime(time: Time): number | null {
    // Default implementation - subclasses should override
    return null;
  }

  /**
   * Clear crosshair position
   */
  clearCrosshair(): void {
    if (!this.chart) return;
    this.chart.clearCrosshairPosition();
  }

  /**
   * Sync time range from another panel
   */
  syncTimeRange(range: LogicalRange | null): void {
    if (!this.chart || !range) return;

    this.isSyncingTimeRange = true;
    try {
      this.chart.timeScale().setVisibleLogicalRange(range);
    } finally {
      setTimeout(() => {
        this.isSyncingTimeRange = false;
      }, 0);
    }
  }

  /**
   * Get the current visible time range
   */
  getVisibleTimeRange(): LogicalRange | null {
    if (!this.chart) return null;
    return this.chart.timeScale().getVisibleLogicalRange();
  }

  /**
   * Resize the chart
   */
  resize(width: number, height: number): void {
    if (!this.chart) return;
    this.chart.resize(width, height);
  }

  /**
   * Fit content to visible area
   */
  fitContent(): void {
    if (!this.chart) return;
    this.chart.timeScale().fitContent();
  }

  /**
   * Get the chart API (for advanced operations)
   */
  getChart(): IChartApi | null {
    return this.chart;
  }

  /**
   * Get panel ID
   */
  getPanelId(): string {
    return this.panelId;
  }

  /**
   * Get panel height configuration
   */
  getHeight(): number {
    return this.config.height;
  }

  /**
   * Set panel height
   */
  setHeight(height: number): void {
    this.config.height = height;
  }

  /**
   * Cleanup - remove chart and listeners
   */
  cleanup(): void {
    if (this.chart) {
      this.chart.remove();
      this.chart = null;
    }
    this.container = null;
    this.onCrosshairMove = null;
    this.onTimeRangeChange = null;
  }

  // ============================================================================
  // Abstract methods - must be implemented by subclasses
  // ============================================================================

  /**
   * Called after chart is initialized - subclasses should setup their series here
   */
  protected abstract onInitialize(): void;

  /**
   * Get the main series for this panel (used for crosshair sync)
   */
  abstract getMainSeries(): ISeriesApi<SeriesType> | null;

  /**
   * Update the panel with new data
   */
  abstract updateData(data: TData): void;

  /**
   * Get the current value at the crosshair position
   */
  abstract getCrosshairValue(time: Time): TCrosshairValue;

  /**
   * Get legend data for display
   * Returns an object with panel-specific legend information
   */
  abstract getLegendData(time: Time): TLegendData;
}

export { CrosshairMode };
