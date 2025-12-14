/**
 * OverlayIndicator - Base class for indicators that overlay on the price chart
 *
 * Examples: SMA, EMA, Bollinger Bands, VWAP, Volume
 * These indicators share the price chart's price scale and appear
 * as lines or histograms on the main chart.
 */

import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  Time,
  LineData,
} from "lightweight-charts";
import { LineSeries, HistogramSeries } from "lightweight-charts";
import { BaseIndicator, type IndicatorData } from "./BaseIndicator";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";

export abstract class OverlayIndicator extends BaseIndicator {
  protected seriesRef: ISeriesApi<"Line"> | ISeriesApi<"Histogram"> | null =
    null;
  protected priceScaleId: string = "right"; // Share price chart's scale

  /**
   * Render indicator as overlay on price chart
   * Default implementation for line series - subclasses can override
   */
  render(chart: IChartApi, data: IndicatorData[]): void {
    this.chart = chart;
    this.data = data;

    if (data.length === 0) return;

    // Convert IndicatorData to LineData format
    const lineData: LineData<Time>[] = data.map((d) => ({
      time: d.time,
      value: d.value,
    }));

    if (this.seriesRef) {
      // Update existing series
      this.seriesRef.setData(lineData);
    } else {
      // Create new series
      this.seriesRef = chart.addSeries(LineSeries, {
        color: this.getColor(),
        lineWidth: this.getLineWidth() as any, // Lightweight Charts v5 type compatibility
        priceScaleId: this.priceScaleId,
        title: this.config.name,
        lastValueVisible: false, // Hide automatic last value - crosshair value shown in legend
      });
      this.seriesRef.setData(lineData);
    }

    this.series = this.seriesRef;
  }

  /**
   * Clean up indicator (remove series)
   */
  cleanup(chart: IChartApi): void {
    if (this.seriesRef) {
      try {
        chart.removeSeries(this.seriesRef);
      } catch {
        // Series may already be removed
      }
      this.seriesRef = null;
    }
    this.series = null;
    this.chart = null;
  }

  /**
   * Get color for indicator line
   * Subclasses can override for custom colors
   */
  protected getColor(): string {
    const type = this.config.type.toLowerCase();
    const colorMap: Record<string, string> = {
      sma: "#3b82f6", // blue
      ema: "#f97316", // orange
      volume: "#22c55e", // green
      vwap: "#06b6d4", // cyan
    };
    return colorMap[type] || "#888";
  }

  /**
   * Get line width
   * Subclasses can override
   */
  protected getLineWidth(): number {
    return 2;
  }

  /**
   * Get price scale ID
   * Default is "right" (price chart scale)
   * Subclasses can override (e.g., Volume uses "volume")
   */
  protected getPriceScaleId(): string {
    return this.priceScaleId;
  }

  /**
   * Get series reference (for crosshair value extraction)
   */
  getSeries(): ISeriesApi<"Line"> | ISeriesApi<"Histogram"> | null {
    return this.seriesRef;
  }
}
