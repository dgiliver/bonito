/**
 * BollingerBandsIndicator - Bollinger Bands overlay indicator
 *
 * Phase 0: Minimal implementation for refactoring
 * Phase 2: Full implementation with area fill
 */

import { OverlayIndicator } from "../base/OverlayIndicator";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";
import type { CandlestickData, Time } from "lightweight-charts";
import type { IndicatorData } from "../base/BaseIndicator";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { LineSeries } from "lightweight-charts";

interface BollingerBandData {
  time: Time;
  upper: number;
  middle: number;
  lower: number;
}

export class BollingerBandsIndicator extends OverlayIndicator {
  private upperSeries: ISeriesApi<"Line"> | null = null;
  private middleSeries: ISeriesApi<"Line"> | null = null;
  private lowerSeries: ISeriesApi<"Line"> | null = null;
  private candleDataRef: { current: CandlestickData<Time>[] } | null = null;

  setCandleDataRef(ref: { current: CandlestickData<Time>[] }): void {
    this.candleDataRef = ref;
  }

  calculate(candleData: CandlestickData<Time>[]): IndicatorData[] {
    // Return middle band as primary data
    const bands = this.calculateBands(candleData);
    return bands.map((b) => ({ time: b.time, value: b.middle }));
  }

  private calculateBands(
    candleData: CandlestickData<Time>[],
  ): BollingerBandData[] {
    if (candleData.length === 0) return [];

    const period = (this.config.params.period as number) || 20;
    const stdDev = (this.config.params.std_dev as number) || 2;
    if (candleData.length < period) return [];

    const bands: BollingerBandData[] = [];
    const closes = candleData.map((d) => d.close);

    for (let i = period - 1; i < candleData.length; i++) {
      const slice = closes.slice(i - period + 1, i + 1);
      const sma = slice.reduce((acc, val) => acc + val, 0) / period;
      const variance =
        slice.reduce((acc, val) => acc + Math.pow(val - sma, 2), 0) / period;
      const std = Math.sqrt(variance);

      bands.push({
        time: candleData[i].time,
        middle: sma,
        upper: sma + std * stdDev,
        lower: sma - std * stdDev,
      });
    }
    return bands;
  }

  render(chart: IChartApi, data: IndicatorData[]): void {
    this.chart = chart;
    this.data = data;

    if (data.length === 0 || !this.chart) return;

    // Get full candle data from chart context (stored separately)
    const bands = this.calculateBands(this.candleDataRef?.current || []);

    if (bands.length === 0) return;

    // Render upper, middle, lower bands
    if (!this.upperSeries) {
      this.upperSeries = chart.addSeries(LineSeries, {
        color: "#E91E63",
        lineWidth: 1,
        lineStyle: 2,
        priceScaleId: "right",
        title: `${this.config.name} Upper`,
        lastValueVisible: false,
      });
      this.middleSeries = chart.addSeries(LineSeries, {
        color: "#2196F3",
        lineWidth: 1,
        priceScaleId: "right",
        title: `${this.config.name} Middle`,
        lastValueVisible: false,
      });
      this.lowerSeries = chart.addSeries(LineSeries, {
        color: "#E91E63",
        lineWidth: 1,
        lineStyle: 2,
        priceScaleId: "right",
        title: `${this.config.name} Lower`,
        lastValueVisible: false,
      });
    }

    if (this.upperSeries) {
      this.upperSeries.setData(
        bands.map((b) => ({ time: b.time, value: b.upper })),
      );
    }
    if (this.middleSeries) {
      this.middleSeries.setData(
        bands.map((b) => ({ time: b.time, value: b.middle })),
      );
    }
    if (this.lowerSeries) {
      this.lowerSeries.setData(
        bands.map((b) => ({ time: b.time, value: b.lower })),
      );
    }

    if (this.upperSeries && this.middleSeries && this.lowerSeries) {
      this.series = new Map([
        ["upper", this.upperSeries],
        ["middle", this.middleSeries],
        ["lower", this.lowerSeries],
      ]) as any; // Type assertion needed for Map<string, ISeriesApi<"Line">>
    }
  }

  cleanup(chart: IChartApi): void {
    if (this.upperSeries) {
      try {
        chart.removeSeries(this.upperSeries);
      } catch {}
      this.upperSeries = null;
    }
    if (this.middleSeries) {
      try {
        chart.removeSeries(this.middleSeries);
      } catch {}
      this.middleSeries = null;
    }
    if (this.lowerSeries) {
      try {
        chart.removeSeries(this.lowerSeries);
      } catch {}
      this.lowerSeries = null;
    }
    this.series = null;
    this.chart = null;
  }

  getStrategyFields(): string[] {
    const period = (this.config.params.period as number) || 20;
    return [`bb_upper_${period}`, `bb_middle_${period}`, `bb_lower_${period}`];
  }

  getAgentContext() {
    return {
      name: this.config.name,
      type: this.config.type,
      params: this.config.params,
      currentValue: this.getCurrentValue(),
    };
  }
}
