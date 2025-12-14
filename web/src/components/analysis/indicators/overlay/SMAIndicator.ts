/**
 * SMAIndicator - Simple Moving Average overlay indicator
 *
 * Phase 0: Minimal implementation for refactoring
 * Phase 2: Full implementation with proper calculation
 */

import { OverlayIndicator } from "../base/OverlayIndicator";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";
import type { CandlestickData, Time } from "lightweight-charts";
import type { IndicatorData } from "../base/BaseIndicator";

export class SMAIndicator extends OverlayIndicator {
  calculate(candleData: CandlestickData<Time>[]): IndicatorData[] {
    if (candleData.length === 0) return [];

    const period = (this.config.params.period as number) || 20;
    if (candleData.length < period) return [];

    const sma: IndicatorData[] = [];
    for (let i = period - 1; i < candleData.length; i++) {
      const sum = candleData
        .slice(i - period + 1, i + 1)
        .reduce((acc, d) => acc + d.close, 0);
      sma.push({
        time: candleData[i].time,
        value: sum / period,
      });
    }
    return sma;
  }

  getStrategyFields(): string[] {
    const period = (this.config.params.period as number) || 20;
    return [`sma_${period}`];
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
