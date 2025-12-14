/**
 * RSIIndicator - Relative Strength Index panel indicator
 *
 * Phase 0: Minimal implementation for refactoring
 * Phase 3: Full implementation with threshold zones
 */

import { PanelIndicator } from "../base/PanelIndicator";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";
import type { CandlestickData, Time } from "lightweight-charts";
import type { IndicatorData } from "../base/BaseIndicator";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { LineSeries, AreaSeries } from "lightweight-charts";

export class RSIIndicator extends PanelIndicator {
  private overboughtLine: ISeriesApi<"Line"> | null = null;
  private oversoldLine: ISeriesApi<"Line"> | null = null;
  private thresholdZoneTop: ISeriesApi<"Area"> | null = null; // Area from 0 to 70 (overbought)
  private thresholdZoneBottom: ISeriesApi<"Area"> | null = null; // Area from 0 to 30 (oversold) - used to mask bottom

  calculate(candleData: CandlestickData<Time>[]): IndicatorData[] {
    if (candleData.length === 0) return [];

    const period = (this.config.params.period as number) || 14;
    if (candleData.length < period + 1) return [];

    const rsi: IndicatorData[] = [];
    let avgGain = 0;
    let avgLoss = 0;

    // Calculate initial average gain/loss
    for (let i = 1; i <= period; i++) {
      const change = candleData[i].close - candleData[i - 1].close;
      if (change > 0) {
        avgGain += change;
      } else {
        avgLoss += Math.abs(change);
      }
    }
    avgGain /= period;
    avgLoss /= period;

    // Calculate initial RSI
    let rs = avgLoss === 0 ? 100 : avgGain / avgLoss; // Handle division by zero
    rsi.push({
      time: candleData[period].time,
      value: 100 - 100 / (1 + rs),
    });

    // Calculate subsequent RSI values
    for (let i = period + 1; i < candleData.length; i++) {
      const change = candleData[i].close - candleData[i - 1].close;
      let gain = 0;
      let loss = 0;
      if (change > 0) {
        gain = change;
      } else {
        loss = Math.abs(change);
      }

      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;

      rs = avgGain / avgLoss;
      rsi.push({
        time: candleData[i].time,
        value: 100 - 100 / (1 + rs),
      });
    }
    return rsi;
  }

  render(chart: IChartApi, data: IndicatorData[]): void {
    super.render(chart, data);

    // #region agent log
    fetch("http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        location: "RSIIndicator.ts:72",
        message: "RSI render",
        data: {
          name: this.config.name,
          dataLength: data.length,
          hasSeries: !!this.series,
          priceScaleId: this.getPriceScaleId(),
          panelOrder: this.getPanelOrder(),
        },
        timestamp: Date.now(),
        sessionId: "debug-session",
        hypothesisId: "H1,H5",
      }),
    }).catch(() => {});
    // #endregion

    if (data.length === 0) return;

    const overbought = (this.config.params.overbought as number) || 70;
    const oversold = (this.config.params.oversold as number) || 30;
    const priceScaleId = this.getPriceScaleId();

    // Fix RSI scale to show 0-100 range
    // CRITICAL: Access scale directly from chart using priceScaleId, not from series
    // This ensures we're configuring the correct scale for the RSI panel
    if (this.series && !(this.series instanceof Map)) {
      const series = this.series as ISeriesApi<"Line">;

      // Verify RSI data range
      const minValue = Math.min(...data.map((d) => d.value));
      const maxValue = Math.max(...data.map((d) => d.value));

      // Use the RSI's unique priceScaleId for its scale
      // The scale auto-scales to RSI data range (0-100)
      const priceScale = chart.priceScale(priceScaleId);

      // #region agent log - BEFORE RSI scale configuration
      let scaleOptionsBeforeRSI: any = {};
      try {
        scaleOptionsBeforeRSI = priceScale.options();
      } catch (e) {
        scaleOptionsBeforeRSI = { error: String(e) };
      }
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: "RSIIndicator.ts:95",
            message: "RSI scale configuration - BEFORE",
            data: {
              priceScaleId,
              minValue,
              maxValue,
              dataLength: data.length,
              scaleOptionsBefore: scaleOptionsBeforeRSI,
              accessMethod: "chart.priceScale(priceScaleId)",
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H2",
          }),
        },
      ).catch(() => {});
      // #endregion

      // Configure scale - autoScale: true will automatically show the data range (0-100 for RSI)
      // Accessing scale directly from chart ensures we're configuring the correct scale
      priceScale.applyOptions({
        autoScale: true, // CRITICAL FIX: Must be true for RSI scale to show 0-100 range
        scaleMargins: { top: 0.8, bottom: 0 }, // No bottom margin - use full bottom 20%
        borderVisible: true,
        borderColor: "rgba(255, 255, 255, 0.1)",
        entireTextOnly: false,
        visible: true, // CRITICAL: Ensure RSI scale is visible
        minimumWidth: 60, // CRITICAL: Overlay scales need minimumWidth to render (web search finding)
      });

      // #region agent log - AFTER RSI scale configuration
      const scaleOptionsAfter = priceScale.options();
      let scaleWidthRSI = 0;
      try {
        scaleWidthRSI = priceScale.width();
      } catch (e) {
        // width() might not be available
      }

      // CRITICAL: Check if series is properly attached to scale
      // In Lightweight Charts, the scale should automatically use the series' data range
      // But we need to verify the series is actually using this scale
      // Note: Lightweight Charts doesn't expose priceScale().id(), but we know it's using priceScaleId
      const seriesData = series.data();
      const seriesDataRange =
        seriesData.length > 0
          ? {
              min: Math.min(...seriesData.map((d) => (d as any).value)),
              max: Math.max(...seriesData.map((d) => (d as any).value)),
            }
          : null;

      // Try to get the scale's visible range (if available)
      let scaleVisibleRange: any = null;
      try {
        // Lightweight Charts doesn't expose visible range directly, but we can check scale options
        scaleVisibleRange = {
          note: "Not directly accessible in Lightweight Charts API",
        };
      } catch (e) {
        scaleVisibleRange = { error: String(e) };
      }

      const logData = {
        location: "RSIIndicator.ts:130",
        message: "RSI scale configuration - AFTER",
        data: {
          priceScaleId,
          autoScale: scaleOptionsAfter.autoScale,
          scaleMargins: scaleOptionsAfter.scaleMargins,
          visible: scaleOptionsAfter.visible,
          scaleWidth: scaleWidthRSI,
          borderVisible: scaleOptionsAfter.borderVisible,
          minValue,
          maxValue,
          seriesDataRange,
          seriesDataLength: seriesData.length,
          scaleVisibleRange,
        },
        timestamp: Date.now(),
        sessionId: "debug-session",
        hypothesisId: "H2",
      };
      console.log("[DEBUG] RSI Scale Configuration", logData);
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(logData),
        },
      ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
      // #endregion

      // CRITICAL FIX: Force scale to recalculate by temporarily disabling and re-enabling autoScale
      // This ensures the scale picks up the RSI data range (0-100) instead of price data
      priceScale.applyOptions({
        autoScale: false, // Temporarily disable
      });
      // Force a small delay to ensure the change takes effect
      setTimeout(() => {
        priceScale.applyOptions({
          autoScale: true, // Re-enable to force recalculation with RSI data
        });
        // #region agent log
        const logData2 = {
          location: "RSIIndicator.ts:150",
          message: "RSI scale autoScale FORCE RECALC",
          data: {
            priceScaleId,
            autoScaleAfter: priceScale.options().autoScale,
          },
          timestamp: Date.now(),
          sessionId: "debug-session",
          hypothesisId: "H2",
        };
        console.log("[DEBUG] RSI Scale Force Recalc", logData2);
        fetch(
          "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(logData2),
          },
        ).catch((e) => console.error("[DEBUG] Log fetch failed:", e));
        // #endregion
      }, 10);
    } else {
      // #region agent log
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: "RSIIndicator.ts:122",
            message: "RSI scale configuration - SKIPPED",
            data: {
              priceScaleId,
              hasSeries: !!this.series,
              isMap: this.series instanceof Map,
            },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H2",
          }),
        },
      ).catch(() => {});
      // #endregion
    }

    // Create threshold zone (shaded area between 30-70) - Robinhood style
    // Use two area series: one from 0-70 (purple), one from 0-30 (background color to mask)
    // The visual difference creates the shaded zone between 30-70
    if (!this.thresholdZoneTop && data.length > 0) {
      // #region agent log
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: "RSIIndicator.ts:100",
            message: "Creating RSI threshold zone",
            data: { priceScaleId, oversold, overbought },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H3",
          }),
        },
      ).catch(() => {});
      // #endregion

      // Create area from 0 to overbought (70) with purple fill
      this.thresholdZoneTop = chart.addSeries(AreaSeries, {
        topColor: "rgba(139, 92, 246, 0.15)", // Light purple fill at top (70)
        bottomColor: "rgba(139, 92, 246, 0.08)", // Medium purple at bottom (30)
        lineColor: "transparent", // No line, just fill
        priceScaleId,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      });

      // Create second area from 0 to oversold (30) with chart background color to mask the bottom
      // This creates the visual effect of a zone between 30-70
      // Use a color that matches the chart background (light mode: white/light, dark mode: dark)
      this.thresholdZoneBottom = chart.addSeries(AreaSeries, {
        topColor: "rgba(255, 255, 255, 1)", // White/light background at top (30) - will blend with chart
        bottomColor: "rgba(255, 255, 255, 1)", // White/light background at bottom (0)
        lineColor: "transparent", // No line, just fill
        priceScaleId,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      });
    }

    // Create threshold lines if they don't exist
    if (!this.overboughtLine && this.series) {
      // #region agent log
      fetch(
        "http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            location: "RSIIndicator.ts:95",
            message: "Creating RSI threshold lines",
            data: { priceScaleId, overbought, oversold },
            timestamp: Date.now(),
            sessionId: "debug-session",
            hypothesisId: "H1,H5",
          }),
        },
      ).catch(() => {});
      // #endregion

      this.overboughtLine = chart.addSeries(LineSeries, {
        color: "rgba(239, 68, 68, 0.6)",
        lineWidth: 1,
        lineStyle: 2,
        priceScaleId,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      });

      this.oversoldLine = chart.addSeries(LineSeries, {
        color: "rgba(34, 197, 94, 0.6)",
        lineWidth: 1,
        lineStyle: 2,
        priceScaleId,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      });
    }

    // Update threshold zone (shaded area between oversold and overbought)
    // Top area: fills from 0 to 70 (overbought) with purple gradient
    // Bottom area: fills from 0 to 30 (oversold) with background color to mask
    // The visual result is a purple zone between 30-70
    if (this.thresholdZoneTop && this.thresholdZoneBottom && data.length > 0) {
      // Top area: purple fill from 0 to 70
      this.thresholdZoneTop.setData(
        data.map((d) => ({
          time: d.time,
          value: overbought, // Top of shaded area (70)
        })),
      );

      // Bottom area: background color fill from 0 to 30 (masks the purple below 30)
      this.thresholdZoneBottom.setData(
        data.map((d) => ({
          time: d.time,
          value: oversold, // Bottom of shaded area (30)
        })),
      );
    }

    // Update threshold lines
    if (this.overboughtLine && this.oversoldLine && data.length > 0) {
      this.overboughtLine.setData(
        data.map((d) => ({ time: d.time, value: overbought })),
      );
      this.oversoldLine.setData(
        data.map((d) => ({ time: d.time, value: oversold })),
      );
    }
  }

  cleanup(chart: IChartApi): void {
    if (this.thresholdZoneTop) {
      try {
        chart.removeSeries(this.thresholdZoneTop);
      } catch {}
      this.thresholdZoneTop = null;
    }
    if (this.thresholdZoneBottom) {
      try {
        chart.removeSeries(this.thresholdZoneBottom);
      } catch {}
      this.thresholdZoneBottom = null;
    }
    if (this.overboughtLine) {
      try {
        chart.removeSeries(this.overboughtLine);
      } catch {}
      this.overboughtLine = null;
    }
    if (this.oversoldLine) {
      try {
        chart.removeSeries(this.oversoldLine);
      } catch {}
      this.oversoldLine = null;
    }
    super.cleanup(chart);
  }

  getStrategyFields(): string[] {
    const period = (this.config.params.period as number) || 14;
    return [`rsi_${period}`];
  }

  getAgentContext() {
    const currentValue = this.getCurrentValue();
    const overbought = (this.config.params.overbought as number) || 70;
    const oversold = (this.config.params.oversold as number) || 30;

    let signal: "buy" | "sell" | "neutral" = "neutral";
    if (currentValue !== null) {
      if (currentValue >= overbought) signal = "sell";
      else if (currentValue <= oversold) signal = "buy";
    }

    return {
      name: this.config.name,
      type: this.config.type,
      params: this.config.params,
      currentValue,
      analysis: {
        currentValue,
        trend: this.getTrend(),
        signal,
        strength: currentValue !== null ? Math.abs(currentValue - 50) * 2 : 0,
        interpretation:
          currentValue !== null
            ? `RSI: ${currentValue.toFixed(2)} ${signal === "buy" ? "(Oversold)" : signal === "sell" ? "(Overbought)" : ""}`
            : "Insufficient data",
      },
    };
  }
}
