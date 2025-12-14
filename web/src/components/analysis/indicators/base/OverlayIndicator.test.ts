/**
 * OverlayIndicator Tests
 *
 * Tests for indicators that overlay on the price chart
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { OverlayIndicator } from "./OverlayIndicator";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";
import type {
  IChartApi,
  CandlestickData,
  Time,
  ISeriesApi,
} from "lightweight-charts";
import { LineSeries } from "lightweight-charts";

// ============================================================================
// Test Implementation
// ============================================================================

class TestOverlayIndicator extends OverlayIndicator {
  calculate(
    candleData: CandlestickData<Time>[],
  ): import("./BaseIndicator").IndicatorData[] {
    return candleData.map((candle) => ({
      time: candle.time,
      value: candle.close,
    }));
  }

  getStrategyFields(): string[] {
    return ["test_overlay"];
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

const mockConfig: IndicatorConfig = {
  type: "sma",
  name: "SMA(20)",
  params: { period: 20 },
  visible: true,
};

const mockCandleData: CandlestickData<Time>[] = [
  { time: 1704067200 as Time, open: 100, high: 105, low: 98, close: 103 },
  { time: 1704153600 as Time, open: 103, high: 108, low: 101, close: 106 },
];

const mockSeries = {
  setData: vi.fn(),
  priceScale: vi.fn(() => ({
    applyOptions: vi.fn(),
  })),
} as unknown as ISeriesApi<"Line">;

const mockChart = {
  addSeries: vi.fn(() => mockSeries),
  removeSeries: vi.fn(),
  timeScale: vi.fn(),
} as unknown as IChartApi;

// ============================================================================
// Tests
// ============================================================================

describe("OverlayIndicator", () => {
  let indicator: TestOverlayIndicator;

  beforeEach(() => {
    vi.clearAllMocks();
    indicator = new TestOverlayIndicator(mockConfig);
  });

  describe("Rendering", () => {
    it("creates line series on first render", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);

      expect(mockChart.addSeries).toHaveBeenCalledWith(LineSeries, {
        color: expect.any(String),
        lineWidth: expect.any(Number),
        priceScaleId: "right",
        title: "SMA(20)",
        lastValueVisible: false,
      });
    });

    it("updates existing series on subsequent renders", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);
      vi.clearAllMocks();

      // Second render should update, not create
      indicator.render(mockChart, data);
      expect(mockChart.addSeries).not.toHaveBeenCalled();
      expect(mockSeries.setData).toHaveBeenCalled();
    });

    it("uses default price scale 'right'", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);

      expect(mockChart.addSeries).toHaveBeenCalledWith(
        LineSeries,
        expect.objectContaining({
          priceScaleId: "right",
        }),
      );
    });

    it("sets correct line data", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);

      expect(mockSeries.setData).toHaveBeenCalledWith([
        { time: 1704067200, value: 103 },
        { time: 1704153600, value: 106 },
      ]);
    });

    it("handles empty data gracefully", () => {
      indicator.render(mockChart, []);
      expect(mockChart.addSeries).not.toHaveBeenCalled();
    });
  });

  describe("Cleanup", () => {
    it("removes series on cleanup", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);
      indicator.cleanup(mockChart);

      expect(mockChart.removeSeries).toHaveBeenCalledWith(mockSeries);
    });

    it("handles cleanup when no series exists", () => {
      expect(() => indicator.cleanup(mockChart)).not.toThrow();
    });

    it("handles cleanup when series already removed", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);
      mockChart.removeSeries = vi.fn(() => {
        throw new Error("Series not found");
      });
      expect(() => indicator.cleanup(mockChart)).not.toThrow();
    });
  });

  describe("Color Configuration", () => {
    it("uses default color for unknown type", () => {
      const unknownConfig: IndicatorConfig = {
        type: "unknown",
        name: "Unknown(10)",
        params: {},
        visible: true,
      };
      const unknownIndicator = new TestOverlayIndicator(unknownConfig);
      const data = unknownIndicator.calculate(mockCandleData);
      unknownIndicator.render(mockChart, data);

      expect(mockChart.addSeries).toHaveBeenCalledWith(
        LineSeries,
        expect.objectContaining({
          color: "#888", // Default color
        }),
      );
    });

    it("uses type-specific color for known types", () => {
      const smaConfig: IndicatorConfig = {
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      };
      const smaIndicator = new TestOverlayIndicator(smaConfig);
      const data = smaIndicator.calculate(mockCandleData);
      smaIndicator.render(mockChart, data);

      expect(mockChart.addSeries).toHaveBeenCalledWith(
        LineSeries,
        expect.objectContaining({
          color: "#3b82f6", // Blue for SMA
        }),
      );
    });
  });

  describe("Series Access", () => {
    it("provides access to series reference", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);

      const series = indicator.getSeries();
      expect(series).toBe(mockSeries);
    });

    it("returns null when no series created", () => {
      expect(indicator.getSeries()).toBeNull();
    });
  });

  describe("Inheritance", () => {
    it("inherits from BaseIndicator", () => {
      expect(indicator).toBeInstanceOf(OverlayIndicator);
      expect(indicator.getName()).toBe("SMA(20)");
      expect(indicator.getType()).toBe("sma");
    });

    it("implements all required methods", () => {
      expect(typeof indicator.calculate).toBe("function");
      expect(typeof indicator.render).toBe("function");
      expect(typeof indicator.cleanup).toBe("function");
      expect(typeof indicator.getStrategyFields).toBe("function");
      expect(typeof indicator.getAgentContext).toBe("function");
    });
  });
});
