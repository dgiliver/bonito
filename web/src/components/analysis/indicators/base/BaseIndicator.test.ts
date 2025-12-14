/**
 * BaseIndicator Tests
 *
 * Comprehensive tests for the abstract base class interface
 * Tests ensure the foundation is bulletproof before building on it
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  BaseIndicator,
  type IndicatorData,
  type IndicatorAnalysis,
} from "./BaseIndicator";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";
import type { IChartApi, CandlestickData, Time } from "lightweight-charts";

// ============================================================================
// Test Implementation (Concrete class for testing abstract base)
// ============================================================================

class TestIndicator extends BaseIndicator {
  calculate(candleData: CandlestickData<Time>[]): IndicatorData[] {
    // Simple test implementation: return close prices
    return candleData.map((candle) => ({
      time: candle.time,
      value: candle.close,
    }));
  }

  render(chart: IChartApi, data: IndicatorData[]): void {
    this.chart = chart;
    this.data = data;
  }

  cleanup(chart: IChartApi): void {
    this.chart = null;
    this.data = [];
  }

  getStrategyFields(): string[] {
    return ["test_ind_value"];
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

// ============================================================================
// Test Data
// ============================================================================

const mockIndicatorConfig: IndicatorConfig = {
  type: "test",
  name: "Test(20)",
  params: { period: 20 },
  visible: true,
};

const mockCandleData: CandlestickData<Time>[] = [
  { time: 1704067200 as Time, open: 100, high: 105, low: 98, close: 103 },
  { time: 1704153600 as Time, open: 103, high: 108, low: 101, close: 106 },
  { time: 1704240000 as Time, open: 106, high: 110, low: 104, close: 109 },
];

const mockChart = {
  addSeries: vi.fn(),
  removeSeries: vi.fn(),
  timeScale: vi.fn(),
} as unknown as IChartApi;

// ============================================================================
// Tests
// ============================================================================

describe("BaseIndicator", () => {
  let indicator: TestIndicator;

  beforeEach(() => {
    indicator = new TestIndicator(mockIndicatorConfig);
  });

  describe("Constructor & Configuration", () => {
    it("initializes with config", () => {
      expect(indicator.getName()).toBe("Test(20)");
      expect(indicator.getType()).toBe("test");
      expect(indicator.isVisible()).toBe(true);
    });

    it("stores config correctly", () => {
      const config = indicator["config"];
      expect(config).toEqual(mockIndicatorConfig);
    });
  });

  describe("Calculation", () => {
    it("calculates indicator data from candles", () => {
      const result = indicator.calculate(mockCandleData);
      expect(result).toHaveLength(3);
      expect(result[0].value).toBe(103);
      expect(result[1].value).toBe(106);
      expect(result[2].value).toBe(109);
    });

    it("handles empty candle data", () => {
      const result = indicator.calculate([]);
      expect(result).toHaveLength(0);
    });

    it("preserves time values", () => {
      const result = indicator.calculate(mockCandleData);
      expect(result[0].time).toBe(1704067200);
      expect(result[1].time).toBe(1704153600);
    });
  });

  describe("Data Management", () => {
    it("updates data correctly", () => {
      const testData: IndicatorData[] = [
        { time: 1704067200 as Time, value: 100 },
        { time: 1704153600 as Time, value: 105 },
      ];
      indicator.updateData(testData);
      expect(indicator.getData()).toEqual(testData);
    });

    it("gets current value from latest data point", () => {
      const testData: IndicatorData[] = [
        { time: 1704067200 as Time, value: 100 },
        { time: 1704153600 as Time, value: 105 },
        { time: 1704240000 as Time, value: 110 },
      ];
      indicator.updateData(testData);
      expect(indicator.getCurrentValue()).toBe(110);
    });

    it("returns null for current value when no data", () => {
      expect(indicator.getCurrentValue()).toBeNull();
    });
  });

  describe("Crosshair Value Extraction", () => {
    beforeEach(() => {
      const testData: IndicatorData[] = [
        { time: 1704067200 as Time, value: 100 },
        { time: 1704153600 as Time, value: 105 },
        { time: 1704240000 as Time, value: 110 },
      ];
      indicator.updateData(testData);
    });

    it("finds exact timestamp match", () => {
      const value = indicator.getCrosshairValue(1704153600);
      expect(value).toBe(105);
    });

    it("finds closest timestamp within 1 day", () => {
      // 12 hours after first data point (closer to second point)
      const value = indicator.getCrosshairValue(1704120000); // ~12 hours after first point
      expect(value).toBe(105); // Should return closest (second point)
    });

    it("returns null for timestamp too far away", () => {
      // 2 days before first data point
      const value = indicator.getCrosshairValue(1703894400);
      expect(value).toBeNull();
    });

    it("returns null when no data", () => {
      indicator.updateData([]);
      const value = indicator.getCrosshairValue(1704153600);
      expect(value).toBeNull();
    });
  });

  describe("Trend Detection", () => {
    it("detects rising trend", () => {
      const testData: IndicatorData[] = [
        { time: 1704067200 as Time, value: 100 },
        { time: 1704153600 as Time, value: 102 },
        { time: 1704240000 as Time, value: 105 },
        { time: 1704326400 as Time, value: 108 },
        { time: 1704412800 as Time, value: 110 },
      ];
      indicator.updateData(testData);
      const trend = indicator["getTrend"]();
      expect(trend).toBe("rising");
    });

    it("detects falling trend", () => {
      const testData: IndicatorData[] = [
        { time: 1704067200 as Time, value: 110 },
        { time: 1704153600 as Time, value: 108 },
        { time: 1704240000 as Time, value: 105 },
        { time: 1704326400 as Time, value: 102 },
        { time: 1704412800 as Time, value: 100 },
      ];
      indicator.updateData(testData);
      const trend = indicator["getTrend"]();
      expect(trend).toBe("falling");
    });

    it("detects sideways trend", () => {
      const testData: IndicatorData[] = [
        { time: 1704067200 as Time, value: 100 },
        { time: 1704153600 as Time, value: 100.5 },
        { time: 1704240000 as Time, value: 99.8 },
        { time: 1704326400 as Time, value: 100.2 },
        { time: 1704412800 as Time, value: 100.1 },
      ];
      indicator.updateData(testData);
      const trend = indicator["getTrend"]();
      expect(trend).toBe("sideways");
    });

    it("returns null for insufficient data", () => {
      indicator.updateData([{ time: 1704067200 as Time, value: 100 }]);
      const trend = indicator["getTrend"]();
      expect(trend).toBeNull();
    });
  });

  describe("Analysis Methods", () => {
    it("provides current analysis", () => {
      const testData: IndicatorData[] = [
        { time: 1704067200 as Time, value: 100 },
        { time: 1704153600 as Time, value: 105 },
      ];
      indicator.updateData(testData);
      const analysis = indicator.getCurrentAnalysis();
      expect(analysis.currentValue).toBe(105);
      expect(analysis.trend).toBe("rising");
      expect(analysis.signal).toBe("neutral");
      expect(analysis.interpretation).toContain("Test(20)");
    });

    it("handles null current value in analysis", () => {
      indicator.updateData([]);
      const analysis = indicator.getCurrentAnalysis();
      expect(analysis.currentValue).toBeNull();
      expect(analysis.interpretation).toBe("Insufficient data");
    });

    it("provides recent analysis", () => {
      const testData: IndicatorData[] = Array.from({ length: 15 }, (_, i) => ({
        time: (1704067200 + i * 86400) as Time,
        value: 100 + i,
      }));
      indicator.updateData(testData);
      const recent = indicator.getRecentAnalysis(10);
      expect(recent).toHaveLength(10);
      expect(recent[0].currentValue).toBe(105); // 10th from end
      expect(recent[9].currentValue).toBe(114); // Last
    });

    it("returns empty array when no data for recent analysis", () => {
      indicator.updateData([]);
      const recent = indicator.getRecentAnalysis(10);
      expect(recent).toHaveLength(0);
    });

    it("detects signals (default empty)", () => {
      const signals = indicator.detectSignals();
      expect(signals).toEqual([]);
    });
  });

  describe("Strategy Integration", () => {
    it("provides strategy fields", () => {
      const fields = indicator.getStrategyFields();
      expect(fields).toEqual(["test_ind_value"]);
    });
  });

  describe("Agent Integration", () => {
    it("provides agent context", () => {
      const testData: IndicatorData[] = [
        { time: 1704067200 as Time, value: 100 },
      ];
      indicator.updateData(testData);
      const context = indicator.getAgentContext();
      expect(context.name).toBe("Test(20)");
      expect(context.type).toBe("test");
      expect(context.currentValue).toBe(100);
      expect(context.params).toEqual({ period: 20 });
    });

    it("handles null current value in context", () => {
      indicator.updateData([]);
      const context = indicator.getAgentContext();
      expect(context.currentValue).toBeNull();
    });
  });

  describe("Lifecycle", () => {
    it("renders indicator on chart", () => {
      indicator.render(mockChart, [{ time: 1704067200 as Time, value: 100 }]);
      expect(indicator["chart"]).toBe(mockChart);
      expect(indicator.getData()).toHaveLength(1);
    });

    it("cleans up indicator", () => {
      indicator.render(mockChart, [{ time: 1704067200 as Time, value: 100 }]);
      indicator.cleanup(mockChart);
      expect(indicator["chart"]).toBeNull();
      expect(indicator.getData()).toHaveLength(0);
    });
  });
});
