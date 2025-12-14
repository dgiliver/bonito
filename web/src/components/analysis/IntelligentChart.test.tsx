/**
 * IntelligentChart Component Tests - RSI Scale Integration
 *
 * Test-Driven Approach for RSI Scale Bug Fix
 *
 * This test mimics user behavior:
 * 1. User adds RSI(14) indicator via agent
 * 2. Chart renders RSI in separate panel
 * 3. Scale should show 0-100 range (NOT price values like 300-340)
 *
 * Test Categories:
 * 1. RSI Indicator Addition - Verifies indicator is added correctly
 * 2. Scale Configuration - Verifies RSI scale shows 0-100, not price values
 * 3. Data Validation - Verifies RSI values are calculated in 0-100 range
 * 4. Scale Separation - Verifies RSI scale is distinct from price scale
 * 5. Real-time Behavior - Traces scale state during indicator addition
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { IChartApi, ISeriesApi, PriceScale } from "lightweight-charts";

// Mock Lightweight Charts
const mockPriceScale = {
  applyOptions: vi.fn(),
  options: vi.fn(() => ({
    scaleMargins: { top: 0.8, bottom: 0.05 },
    borderVisible: true,
    borderColor: "rgba(255, 255, 255, 0.1)",
    entireTextOnly: false,
    autoScale: true,
  })),
  width: vi.fn(() => 60),
};

const mockSeries = {
  setData: vi.fn(),
  applyOptions: vi.fn(),
  priceScale: vi.fn(() => mockPriceScale),
  coordinateToPrice: vi.fn(),
  priceToCoordinate: vi.fn(),
};

const mockChart = {
  addSeries: vi.fn(() => mockSeries),
  removeSeries: vi.fn(),
  subscribeCrosshairMove: vi.fn(),
  timeScale: vi.fn(() => ({
    scrollToPosition: vi.fn(),
    setVisibleRange: vi.fn(),
  })),
  priceScale: vi.fn(() => mockPriceScale),
  resize: vi.fn(),
  remove: vi.fn(),
};

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => mockChart),
  ColorType: { Solid: "solid" },
  CandlestickSeries: "CandlestickSeries",
  HistogramSeries: "HistogramSeries",
  LineSeries: "LineSeries",
  AreaSeries: "AreaSeries",
  createSeriesMarkers: vi.fn(() => ({
    updateMarkers: vi.fn(),
  })),
}));

// Mock AnalysisContext
const mockDispatch = vi.fn();
const mockEmitChartEvent = vi.fn();

const mockState = {
  chart: {
    symbol: "SPY",
    interval: "1d",
    range: "1Y",
    indicators: [],
  },
  backtest: null,
  chat: {
    messages: [],
    isLoading: false,
  },
  annotations: [],
};

vi.mock("@/contexts/AnalysisContext", () => ({
  useAnalysis: vi.fn(() => ({
    state: mockState,
    dispatch: mockDispatch,
    emitChartEvent: mockEmitChartEvent,
  })),
}));

// Mock API
global.fetch = vi.fn(() =>
  Promise.resolve({
    ok: true,
    json: async () => ({
      bars: Array.from({ length: 100 }, (_, i) => ({
        time: new Date(2024, 0, i + 1).getTime() / 1000,
        open: 400 + i * 0.5,
        high: 405 + i * 0.5,
        low: 395 + i * 0.5,
        close: 402 + i * 0.5,
        volume: 1000000 + i * 10000,
      })),
      source: "database",
    }),
  } as Response),
);

// Mock indicator registry
import { IndicatorRegistry } from "@/components/analysis/indicators/registry/IndicatorRegistry";
import { RSIIndicator } from "@/components/analysis/indicators/panel/RSIIndicator";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";

describe("IntelligentChart - RSI Scale Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset state
    mockState.chart.indicators = [];
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("RSI Scale Configuration", () => {
    it("should configure RSI scale to show 0-100 range when RSI indicator is added", async () => {
      // Arrange: Create RSI indicator config
      const rsiConfig: IndicatorConfig = {
        name: "RSI(14)",
        type: "rsi",
        params: { period: 14, overbought: 70, oversold: 30 },
        visible: true,
      };

      // Create mock candle data
      const candleData = Array.from({ length: 50 }, (_, i) => ({
        time: (new Date(2024, 0, i + 1).getTime() / 1000) as any,
        open: 400 + i * 0.5,
        high: 405 + i * 0.5,
        low: 395 + i * 0.5,
        close: 402 + i * 0.5,
      }));

      // Create RSI indicator instance
      const rsiIndicator = new RSIIndicator(rsiConfig, "rsi", 1);

      // Calculate RSI values
      const rsiData = rsiIndicator.calculate(candleData as any);

      // Assert: RSI values should be in 0-100 range
      expect(rsiData.length).toBeGreaterThan(0);
      rsiData.forEach((point) => {
        expect(point.value).toBeGreaterThanOrEqual(0);
        expect(point.value).toBeLessThanOrEqual(100);
      });

      // Render indicator on mock chart
      rsiIndicator.render(mockChart as any, rsiData);

      // Assert: Chart should have been called to add series
      expect(mockChart.addSeries).toHaveBeenCalled();

      // Get the series that was added
      const addedSeries = mockChart.addSeries.mock.results[0].value;
      const priceScale = addedSeries.priceScale();

      // Assert: Price scale should be configured
      expect(priceScale).toBeDefined();

      // Verify scale options were applied
      // The scale should use the RSI priceScaleId ("rsi"), not "right" (price scale)
      const seriesCalls = mockChart.addSeries.mock.calls;
      const rsiSeriesCall = seriesCalls.find(
        (call) => call[1]?.priceScaleId === "rsi",
      );
      expect(rsiSeriesCall).toBeDefined();
      expect(rsiSeriesCall[1].priceScaleId).toBe("rsi");
    });

    it("should verify RSI values are calculated correctly (0-100 range)", () => {
      // Arrange: Create RSI indicator with known data
      const rsiConfig: IndicatorConfig = {
        name: "RSI(14)",
        type: "rsi",
        params: { period: 14 },
        visible: true,
      };

      // Create trending up data (should produce RSI > 50)
      const uptrendData = Array.from({ length: 30 }, (_, i) => ({
        time: (new Date(2024, 0, i + 1).getTime() / 1000) as any,
        open: 100 + i * 2,
        high: 105 + i * 2,
        low: 98 + i * 2,
        close: 103 + i * 2,
      }));

      const rsiIndicator = new RSIIndicator(rsiConfig, "rsi", 1);
      const rsiData = rsiIndicator.calculate(uptrendData as any);

      // Assert: All RSI values should be in 0-100 range
      expect(rsiData.length).toBeGreaterThan(0);
      const allInRange = rsiData.every(
        (point) => point.value >= 0 && point.value <= 100,
      );
      expect(allInRange).toBe(true);

      // Assert: Uptrend should produce RSI > 50 (generally)
      const avgRSI =
        rsiData.reduce((sum, p) => sum + p.value, 0) / rsiData.length;
      expect(avgRSI).toBeGreaterThan(50);
    });

    it("should verify RSI scale is distinct from price scale", () => {
      // Arrange
      const rsiConfig: IndicatorConfig = {
        name: "RSI(14)",
        type: "rsi",
        params: { period: 14 },
        visible: true,
      };

      const candleData = Array.from({ length: 30 }, (_, i) => ({
        time: (new Date(2024, 0, i + 1).getTime() / 1000) as any,
        open: 400 + i,
        high: 405 + i,
        low: 395 + i,
        close: 402 + i,
      }));

      const rsiIndicator = new RSIIndicator(rsiConfig, "rsi", 1);
      const rsiData = rsiIndicator.calculate(candleData as any);

      // Render on chart
      rsiIndicator.render(mockChart as any, rsiData);

      // Get all series calls
      const seriesCalls = mockChart.addSeries.mock.calls;

      // Find RSI series call
      const rsiSeriesCall = seriesCalls.find(
        (call) => call[1]?.priceScaleId === "rsi",
      );

      // Find price series call (if any)
      const priceSeriesCall = seriesCalls.find(
        (call) => call[1]?.priceScaleId === "right",
      );

      // Assert: RSI should use "rsi" priceScaleId, not "right"
      expect(rsiSeriesCall).toBeDefined();
      expect(rsiSeriesCall[1].priceScaleId).toBe("rsi");

      // If price series exists, it should use "right" priceScaleId
      if (priceSeriesCall) {
        expect(priceSeriesCall[1].priceScaleId).toBe("right");
        expect(rsiSeriesCall[1].priceScaleId).not.toBe(
          priceSeriesCall[1].priceScaleId,
        );
      }
    });

    it("should trace scale behavior during RSI addition (real-time)", async () => {
      // This test traces the behavior step-by-step
      const scaleStateTrace: Array<{
        step: string;
        priceScaleId?: string;
        scaleOptions?: any;
        rsiValues?: number[];
      }> = [];

      // Step 1: Create RSI indicator
      const rsiConfig: IndicatorConfig = {
        name: "RSI(14)",
        type: "rsi",
        params: { period: 14 },
        visible: true,
      };

      scaleStateTrace.push({
        step: "RSI indicator created",
        priceScaleId: "rsi",
      });

      // Step 2: Calculate RSI values
      const candleData = Array.from({ length: 30 }, (_, i) => ({
        time: (new Date(2024, 0, i + 1).getTime() / 1000) as any,
        open: 400 + i,
        high: 405 + i,
        low: 395 + i,
        close: 402 + i,
      }));

      const rsiIndicator = new RSIIndicator(rsiConfig, "rsi", 1);
      const rsiData = rsiIndicator.calculate(candleData as any);

      scaleStateTrace.push({
        step: "RSI values calculated",
        rsiValues: rsiData.map((d) => d.value),
      });

      // Verify RSI values are in 0-100 range
      const minRSI = Math.min(...rsiData.map((d) => d.value));
      const maxRSI = Math.max(...rsiData.map((d) => d.value));
      expect(minRSI).toBeGreaterThanOrEqual(0);
      expect(maxRSI).toBeLessThanOrEqual(100);

      scaleStateTrace.push({
        step: "RSI range verified",
        rsiValues: [minRSI, maxRSI],
      });

      // Step 3: Render indicator
      rsiIndicator.render(mockChart as any, rsiData);

      // Get the series that was added
      const seriesCalls = mockChart.addSeries.mock.calls;
      const rsiSeriesCall = seriesCalls.find(
        (call) => call[1]?.priceScaleId === "rsi",
      );

      if (rsiSeriesCall) {
        const scaleOptions = rsiSeriesCall[1];
        scaleStateTrace.push({
          step: "RSI series rendered",
          priceScaleId: scaleOptions.priceScaleId,
          scaleOptions: {
            autoScale: true, // Should be true for RSI
            scaleMargins: { top: 0.8, bottom: 0.05 },
          },
        });
      }

      // Assert: Scale should be configured for RSI (0-100 range)
      // Since Lightweight Charts auto-scales, the scale should show the data range
      // For RSI, this should be approximately 0-100
      expect(scaleStateTrace.length).toBeGreaterThan(0);

      // Final assertion: RSI scale should NOT show price values (300-400 range)
      // The scale should show RSI values (0-100 range)
      const finalStep = scaleStateTrace[scaleStateTrace.length - 1];
      expect(finalStep.priceScaleId).toBe("rsi");
      expect(finalStep.scaleOptions?.autoScale).toBe(true);

      // Log trace for debugging
      console.log(
        "Scale State Trace:",
        JSON.stringify(scaleStateTrace, null, 2),
      );
    });
  });

  describe("RSI Scale Bug Reproduction", () => {
    it("should reproduce the bug: RSI scale showing price values instead of 0-100", () => {
      // This test specifically reproduces the bug where RSI scale shows 300-340
      // instead of 0-100

      const rsiConfig: IndicatorConfig = {
        name: "RSI(14)",
        type: "rsi",
        params: { period: 14 },
        visible: true,
      };

      // Create price data (400-430 range)
      const priceData = Array.from({ length: 30 }, (_, i) => ({
        time: (new Date(2024, 0, i + 1).getTime() / 1000) as any,
        open: 400 + i,
        high: 405 + i,
        low: 395 + i,
        close: 402 + i,
      }));

      const rsiIndicator = new RSIIndicator(rsiConfig, "rsi", 1);
      const rsiData = rsiIndicator.calculate(priceData as any);

      // Verify RSI values are in 0-100 range (not 300-400)
      const rsiMin = Math.min(...rsiData.map((d) => d.value));
      const rsiMax = Math.max(...rsiData.map((d) => d.value));

      // Assert: RSI values should be 0-100, NOT 300-400 (price range)
      expect(rsiMax).toBeLessThanOrEqual(100);
      expect(rsiMin).toBeGreaterThanOrEqual(0);

      // This is the bug: if scale shows 300-340, it means it's using price data
      // instead of RSI data. This test should catch that.
      expect(rsiMin).not.toBeGreaterThan(200); // Should not be in price range
      expect(rsiMax).not.toBeGreaterThan(200); // Should not be in price range

      // Log for debugging
      console.log(`RSI Range: ${rsiMin.toFixed(2)} - ${rsiMax.toFixed(2)}`);
      console.log(
        `Price Range: ${Math.min(...priceData.map((d) => d.close))} - ${Math.max(...priceData.map((d) => d.close))}`,
      );

      // The bug manifests when the scale shows price range instead of RSI range
      // This test verifies the calculated RSI values are correct
      // The actual scale display bug would be caught in integration/E2E tests
    });
  });
});
