/**
 * PanelIndicator - Base class for indicators that render in separate panels
 *
 * Examples: RSI, MACD, Stochastic, ADX, ATR
 * These indicators have their own price scales and appear in separate
 * chart panels below the main price chart.
 */

import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  Time,
  LineData,
} from "lightweight-charts";
import { LineSeries } from "lightweight-charts";
import { BaseIndicator, type IndicatorData } from "./BaseIndicator";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";

export abstract class PanelIndicator extends BaseIndicator {
  protected seriesRef:
    | ISeriesApi<"Line">
    | Map<string, ISeriesApi<"Line">>
    | null = null;
  protected priceScaleId: string; // Unique price scale ID for this panel
  protected panelHeight: number = 0.25; // 25% of viewport height (default)
  protected panelOrder: number; // Display order (lower = higher on screen)

  constructor(
    config: IndicatorConfig,
    priceScaleId: string,
    panelOrder: number,
  ) {
    super(config);
    this.priceScaleId = priceScaleId;
    this.panelOrder = panelOrder;
  }

  /**
   * Render indicator in separate panel
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

    if (this.seriesRef && !(this.seriesRef instanceof Map)) {
      // Update existing series
      this.seriesRef.setData(lineData);
    } else {
      // Create new series with unique price scale
      // #region agent log
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: "PanelIndicator.ts:47",
            message: "Creating panel series",
            data: {
              name: this.config.name,
              priceScaleId: this.priceScaleId,
              panelOrder: this.panelOrder,
              dataLength: lineData.length,
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H1",
          }),
        },
      ).catch(() => {});
      // #endregion

      // Panel indicators use their own priceScaleId on the RIGHT side
      // Lightweight Charts supports multiple overlay scales that can each have their own data range
      // We use scaleMargins to position panels in different vertical areas
      // Each panel's priceScaleId creates a unique scale with its own auto-scaling range
      const series = chart.addSeries(LineSeries, {
        color: this.getColor(),
        lineWidth: this.getLineWidth() as any, // Lightweight Charts v5 type compatibility
        priceScaleId: this.priceScaleId, // Use unique priceScaleId for this panel (e.g., "rsi")
        title: this.config.name,
        lastValueVisible: true, // Show value on right side when hovered
      });

      // CRITICAL: Set data BEFORE configuring scale
      // This ensures the scale can see the data when it auto-scales
      series.setData(lineData);

      // #region agent log - Verify series data and scale binding
      const seriesDataAfter = series.data();
      const seriesDataRange =
        seriesDataAfter.length > 0
          ? {
              min: Math.min(...seriesDataAfter.map((d) => (d as any).value)),
              max: Math.max(...seriesDataAfter.map((d) => (d as any).value)),
            }
          : null;
      const logDataSeries = {
        location: "PanelIndicator.ts:65",
        message: "Panel series data set",
        data: {
          name: this.config.name,
          priceScaleId: this.priceScaleId,
          seriesDataLength: seriesDataAfter.length,
          seriesDataRange,
          lineDataLength: lineData.length,
          lineDataRange:
            lineData.length > 0
              ? {
                  min: Math.min(...lineData.map((d) => d.value)),
                  max: Math.max(...lineData.map((d) => d.value)),
                }
              : null,
        },
        timestamp: Date.now(),
        sessionId: "debug-session",
        hypothesisId: "H1",
      };
      console.log("[DEBUG] Panel Series Data", logDataSeries);
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(logDataSeries),
        },
      ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
      // #endregion

      // Configure the panel's unique price scale AFTER data is set
      // Each panel indicator uses its own priceScaleId which creates a unique scale
      // The scale auto-scales to the series data range (e.g., 0-100 for RSI)
      // scaleMargins control where this panel appears vertically on the chart
      const priceScale = chart.priceScale(this.priceScaleId);

      // Configure scale options - ensure visible and autoScale are set
      // #region agent log - BEFORE scale configuration
      let scaleOptionsBefore: any = {};
      try {
        scaleOptionsBefore = priceScale.options();
      } catch (e) {
        scaleOptionsBefore = { error: String(e) };
      }
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: "PanelIndicator.ts:88",
            message: "Panel scale configuration - BEFORE",
            data: {
              name: this.config.name,
              priceScaleId: this.priceScaleId,
              dataLength: lineData.length,
              dataMin: Math.min(...lineData.map((d) => d.value)),
              dataMax: Math.max(...lineData.map((d) => d.value)),
              scaleOptionsBefore,
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H1,H2",
          }),
        },
      ).catch(() => {});
      // #endregion

      priceScale.applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 }, // Panel starts at 80% of chart, uses bottom 20% (no white space)
        borderVisible: true, // Show border to clearly separate scales (Robinhood style)
        borderColor: "rgba(255, 255, 255, 0.1)", // Subtle border
        entireTextOnly: false, // Show all scale labels
        autoScale: true, // Auto-scale based on visible data (RSI will override this)
        visible: true, // CRITICAL: Make panel scale visible (default might be false for custom priceScaleIds)
        minimumWidth: 60, // CRITICAL: Overlay scales need minimumWidth to render (web search finding)
        // CRITICAL: Ensure the scale uses the series' data range, not the price data range
        // In Lightweight Charts, when autoScale is true, the scale should automatically
        // use the data range of all series attached to it
      });

      // CRITICAL: Force the scale to recalculate by updating the series data again
      // This ensures the scale picks up the correct data range
      // We need to trigger a recalculation by temporarily toggling autoScale
      setTimeout(() => {
        priceScale.applyOptions({
          autoScale: false,
        });
        setTimeout(() => {
          priceScale.applyOptions({
            autoScale: true,
          });
          // #region agent log
          const logDataRecalc = {
            location: "PanelIndicator.ts:115",
            message: "Panel scale FORCE RECALC",
            data: {
              name: this.config.name,
              priceScaleId: this.priceScaleId,
              autoScaleAfter: priceScale.options().autoScale,
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H1",
          };
          console.log("[DEBUG] Panel Scale Force Recalc", logDataRecalc);
          fetch(
            "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(logDataRecalc),
            },
          ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
          // #endregion
        }, 10);
      }, 50);

      // #region agent log - AFTER scale configuration
      const scaleOptions = priceScale.options();
      let scaleWidth = 0;
      try {
        scaleWidth = priceScale.width();
      } catch (e) {
        // width() might not be available immediately after creation
      }
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: "PanelIndicator.ts:105",
            message: "Panel scale configuration - AFTER",
            data: {
              name: this.config.name,
              priceScaleId: this.priceScaleId,
              scaleMargins: scaleOptions.scaleMargins,
              autoScale: scaleOptions.autoScale,
              visible: scaleOptions.visible,
              scaleWidth,
              borderVisible: scaleOptions.borderVisible,
              dataMin: Math.min(...lineData.map((d) => d.value)),
              dataMax: Math.max(...lineData.map((d) => d.value)),
              accessMethod: "chart.priceScale(priceScaleId)",
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H1,H2",
          }),
        },
      ).catch(() => {});
      // #endregion

      // #region agent log
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: "PanelIndicator.ts:85",
            message: "Panel series created",
            data: {
              name: this.config.name,
              priceScaleId: this.priceScaleId,
              hasSeries: !!series,
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H1",
          }),
        },
      ).catch(() => {});
      // #endregion

      this.seriesRef = series;
    }

    this.series = this.seriesRef;
  }

  /**
   * Clean up indicator (remove series and price scale)
   */
  cleanup(chart: IChartApi): void {
    if (this.seriesRef) {
      try {
        if (this.seriesRef instanceof Map) {
          // Multiple series (e.g., MACD has line + signal + histogram)
          this.seriesRef.forEach((series) => {
            chart.removeSeries(series);
          });
        } else {
          chart.removeSeries(this.seriesRef);
        }
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
      rsi: "#8b5cf6", // purple
      macd: "#22c55e", // green
      stoch: "#3b82f6", // blue
      adx: "#f59e0b", // amber
      atr: "#00BCD4", // cyan
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
   * Get price scale ID (unique for this panel)
   * Each panel indicator has its own priceScaleId for its unique scale
   */
  getPriceScaleId(): string {
    return this.priceScaleId;
  }

  /**
   * Get panel height (as fraction of viewport)
   */
  getPanelHeight(): number {
    return this.panelHeight;
  }

  /**
   * Set panel height
   */
  setPanelHeight(height: number): void {
    this.panelHeight = height;
  }

  /**
   * Get panel display order
   */
  getPanelOrder(): number {
    return this.panelOrder;
  }

  /**
   * Get series reference (for crosshair value extraction)
   */
  getSeries(): ISeriesApi<"Line"> | Map<string, ISeriesApi<"Line">> | null {
    return this.seriesRef;
  }
}
