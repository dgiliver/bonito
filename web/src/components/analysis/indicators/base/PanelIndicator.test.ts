/**
 * PanelIndicator Tests
 *
 * Tests for indicators that render in separate panels
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { PanelIndicator } from "./PanelIndicator";
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

class TestPanelIndicator extends PanelIndicator {
  calculate(
    candleData: CandlestickData<Time>[],
  ): import("./BaseIndicator").IndicatorData[] {
    return candleData.map((candle) => ({
      time: candle.time,
      value: candle.close,
    }));
  }

  getStrategyFields(): string[] {
    return ["test_panel"];
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
  type: "rsi",
  name: "RSI(14)",
  params: { period: 14 },
  visible: true,
};

const mockCandleData: CandlestickData<Time>[] = [
  { time: 1704067200 as Time, open: 100, high: 105, low: 98, close: 103 },
  { time: 1704153600 as Time, open: 103, high: 108, low: 101, close: 106 },
];

const mockPriceScale = {
  applyOptions: vi.fn(),
};

const mockSeries = {
  setData: vi.fn(),
  priceScale: vi.fn(() => mockPriceScale),
} as unknown as ISeriesApi<"Line">;

const mockChart = {
  addSeries: vi.fn(() => mockSeries),
  removeSeries: vi.fn(),
  timeScale: vi.fn(),
} as unknown as IChartApi;

// ============================================================================
// Tests
// ============================================================================

describe("PanelIndicator", () => {
  let indicator: TestPanelIndicator;

  beforeEach(() => {
    vi.clearAllMocks();
    indicator = new TestPanelIndicator(mockConfig, "rsi", 1);
  });

  describe("Constructor", () => {
    it("initializes with price scale ID", () => {
      expect(indicator.getPriceScaleId()).toBe("rsi");
    });

    it("initializes with panel order", () => {
      expect(indicator.getPanelOrder()).toBe(1);
    });

    it("uses default panel height", () => {
      expect(indicator.getPanelHeight()).toBe(0.25);
    });

    it("allows custom panel height", () => {
      indicator.setPanelHeight(0.3);
      expect(indicator.getPanelHeight()).toBe(0.3);
    });
  });

  describe("Rendering", () => {
    it("creates line series with unique price scale", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);

      expect(mockChart.addSeries).toHaveBeenCalledWith(LineSeries, {
        color: expect.any(String),
        lineWidth: expect.any(Number),
        priceScaleId: "rsi",
        title: "RSI(14)",
        lastValueVisible: false,
      });
    });

    it("configures price scale margins for panel", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);

      expect(mockPriceScale.applyOptions).toHaveBeenCalledWith({
        scaleMargins: { top: 0.8, bottom: 0 },
        borderVisible: false,
      });
    });

    it("updates existing series on subsequent renders", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);
      vi.clearAllMocks();

      indicator.render(mockChart, data);
      expect(mockChart.addSeries).not.toHaveBeenCalled();
      expect(mockSeries.setData).toHaveBeenCalled();
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
  });

  describe("Panel Management", () => {
    it("returns correct price scale ID", () => {
      expect(indicator.getPriceScaleId()).toBe("rsi");
    });

    it("returns correct panel order", () => {
      const indicator2 = new TestPanelIndicator(mockConfig, "macd", 2);
      expect(indicator2.getPanelOrder()).toBe(2);
      expect(indicator.getPanelOrder()).toBe(1);
    });

    it("allows panel height modification", () => {
      indicator.setPanelHeight(0.4);
      expect(indicator.getPanelHeight()).toBe(0.4);
    });
  });

  describe("Color Configuration", () => {
    it("uses type-specific color for RSI", () => {
      const data = indicator.calculate(mockCandleData);
      indicator.render(mockChart, data);

      expect(mockChart.addSeries).toHaveBeenCalledWith(
        LineSeries,
        expect.objectContaining({
          color: "#8b5cf6", // Purple for RSI
        }),
      );
    });

    it("uses default color for unknown panel type", () => {
      const unknownConfig: IndicatorConfig = {
        type: "unknown",
        name: "Unknown(10)",
        params: {},
        visible: true,
      };
      const unknownIndicator = new TestPanelIndicator(
        unknownConfig,
        "unknown",
        99,
      );
      const data = unknownIndicator.calculate(mockCandleData);
      unknownIndicator.render(mockChart, data);

      expect(mockChart.addSeries).toHaveBeenCalledWith(
        LineSeries,
        expect.objectContaining({
          color: "#888", // Default color
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
      expect(indicator).toBeInstanceOf(PanelIndicator);
      expect(indicator.getName()).toBe("RSI(14)");
      expect(indicator.getType()).toBe("rsi");
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
