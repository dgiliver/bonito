/**
 * EMAIndicator - Exponential Moving Average overlay indicator
 *
 * Phase 0: Minimal implementation for refactoring
 * Phase 2: Full implementation with proper calculation
 */

import { OverlayIndicator } from "../base/OverlayIndicator";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";
import type { CandlestickData, Time } from "lightweight-charts";
import type { IndicatorData } from "../base/BaseIndicator";

export class EMAIndicator extends OverlayIndicator {
  calculate(candleData: CandlestickData<Time>[]): IndicatorData[] {
    if (candleData.length === 0) return [];

    const period = (this.config.params.period as number) || 12;
    if (candleData.length < period) return [];

    const ema: IndicatorData[] = [];
    const multiplier = 2 / (period + 1);
    let sma =
      candleData.slice(0, period).reduce((acc, d) => acc + d.close, 0) / period;
    ema.push({ time: candleData[period - 1].time, value: sma });

    for (let i = period; i < candleData.length; i++) {
      const nextEma =
        (candleData[i].close - ema[ema.length - 1].value) * multiplier +
        ema[ema.length - 1].value;
      ema.push({ time: candleData[i].time, value: nextEma });
    }
    return ema;
  }

  getStrategyFields(): string[] {
    const period = (this.config.params.period as number) || 12;
    return [`ema_${period}`];
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
