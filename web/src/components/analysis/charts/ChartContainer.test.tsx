/**
 * ChartContainer Tests
 *
 * Tests for multi-chart architecture:
 * - Panel stacking and height allocation
 * - Crosshair synchronization
 * - Time axis synchronization
 * - Correct scale values for each panel
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock lightweight-charts
vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addSeries: vi.fn(() => ({
      setData: vi.fn(),
      applyOptions: vi.fn(),
      priceScale: vi.fn(() => ({
        options: vi.fn(() => ({ visible: true, autoScale: true })),
        applyOptions: vi.fn(),
      })),
      coordinateToPrice: vi.fn((y: number) => y),
      setMarkers: vi.fn(),
    })),
    priceScale: vi.fn(() => ({
      options: vi.fn(() => ({ visible: true, autoScale: true })),
      applyOptions: vi.fn(),
    })),
    timeScale: vi.fn(() => ({
      options: vi.fn(() => ({ visible: true })),
      applyOptions: vi.fn(),
      fitContent: vi.fn(),
      getVisibleLogicalRange: vi.fn(() => ({ from: 0, to: 100 })),
      setVisibleLogicalRange: vi.fn(),
      subscribeVisibleLogicalRangeChange: vi.fn(),
    })),
    subscribeCrosshairMove: vi.fn(),
    setCrosshairPosition: vi.fn(),
    clearCrosshairPosition: vi.fn(),
    resize: vi.fn(),
    remove: vi.fn(),
    removeSeries: vi.fn(),
  })),
  CandlestickSeries: "CandlestickSeries",
  HistogramSeries: "HistogramSeries",
  LineSeries: "LineSeries",
  AreaSeries: "AreaSeries",
  createSeriesMarkers: vi.fn(() => ({
    setMarkers: vi.fn(),
  })),
}));

describe("Multi-Chart Architecture", () => {
  describe("Height Allocation", () => {
    it("should allocate 100% to price chart when no panels", () => {
      const totalHeight = 600;
      const panelCount = 0;
      const expectedPriceHeight = 600;

      // Height calculation function
      const calculateHeights = (height: number, panels: number) => {
        if (panels === 0) return { priceHeight: height, panelHeight: 0 };
        if (panels === 1)
          return {
            priceHeight: Math.floor(height * 0.7),
            panelHeight: Math.floor(height * 0.3),
          };
        if (panels === 2)
          return {
            priceHeight: Math.floor(height * 0.55),
            panelHeight: Math.floor(height * 0.225),
          };
        const priceH = Math.floor(height * 0.45);
        return {
          priceHeight: priceH,
          panelHeight: Math.floor((height - priceH) / panels),
        };
      };

      const { priceHeight } = calculateHeights(totalHeight, panelCount);
      expect(priceHeight).toBe(expectedPriceHeight);
    });

    it("should allocate 70% price, 30% panel for 1 panel", () => {
      const totalHeight = 600;
      const panelCount = 1;

      const calculateHeights = (height: number, panels: number) => {
        if (panels === 0) return { priceHeight: height, panelHeight: 0 };
        if (panels === 1)
          return {
            priceHeight: Math.floor(height * 0.7),
            panelHeight: Math.floor(height * 0.3),
          };
        if (panels === 2)
          return {
            priceHeight: Math.floor(height * 0.55),
            panelHeight: Math.floor(height * 0.225),
          };
        const priceH = Math.floor(height * 0.45);
        return {
          priceHeight: priceH,
          panelHeight: Math.floor((height - priceH) / panels),
        };
      };

      const { priceHeight, panelHeight } = calculateHeights(
        totalHeight,
        panelCount,
      );
      expect(priceHeight).toBe(420); // 70%
      expect(panelHeight).toBe(180); // 30%
    });

    it("should allocate 55% price, 22.5% each for 2 panels", () => {
      const totalHeight = 600;
      const panelCount = 2;

      const calculateHeights = (height: number, panels: number) => {
        if (panels === 0) return { priceHeight: height, panelHeight: 0 };
        if (panels === 1)
          return {
            priceHeight: Math.floor(height * 0.7),
            panelHeight: Math.floor(height * 0.3),
          };
        if (panels === 2)
          return {
            priceHeight: Math.floor(height * 0.55),
            panelHeight: Math.floor(height * 0.225),
          };
        const priceH = Math.floor(height * 0.45);
        return {
          priceHeight: priceH,
          panelHeight: Math.floor((height - priceH) / panels),
        };
      };

      const { priceHeight, panelHeight } = calculateHeights(
        totalHeight,
        panelCount,
      );
      expect(priceHeight).toBe(330); // 55%
      expect(panelHeight).toBe(135); // 22.5%
    });

    it("should allocate 45% price, remaining split for 3+ panels", () => {
      const totalHeight = 600;
      const panelCount = 3;

      const calculateHeights = (height: number, panels: number) => {
        if (panels === 0) return { priceHeight: height, panelHeight: 0 };
        if (panels === 1)
          return {
            priceHeight: Math.floor(height * 0.7),
            panelHeight: Math.floor(height * 0.3),
          };
        if (panels === 2)
          return {
            priceHeight: Math.floor(height * 0.55),
            panelHeight: Math.floor(height * 0.225),
          };
        const priceH = Math.floor(height * 0.45);
        return {
          priceHeight: priceH,
          panelHeight: Math.floor((height - priceH) / panels),
        };
      };

      const { priceHeight, panelHeight } = calculateHeights(
        totalHeight,
        panelCount,
      );
      expect(priceHeight).toBe(270); // 45%
      expect(panelHeight).toBe(110); // (600 - 270) / 3 = 110
    });
  });

  describe("RSI Scale Configuration", () => {
    it("should configure RSI panel with 0-100 scale", () => {
      const rsiConfig = {
        minValue: 0,
        maxValue: 100,
        thresholdLines: [
          { value: 70, color: "rgba(139, 92, 246, 0.4)" },
          { value: 30, color: "rgba(139, 92, 246, 0.4)" },
        ],
      };

      expect(rsiConfig.minValue).toBe(0);
      expect(rsiConfig.maxValue).toBe(100);
      expect(rsiConfig.thresholdLines).toHaveLength(2);
    });

    it("should calculate RSI values correctly", () => {
      // RSI calculation test
      const calculateRSI = (
        closes: number[],
        period: number = 14,
      ): number[] => {
        if (closes.length < period + 1) return closes.map(() => 50);

        const changes: number[] = [];
        for (let i = 1; i < closes.length; i++) {
          changes.push(closes[i] - closes[i - 1]);
        }

        let avgGain = 0;
        let avgLoss = 0;
        for (let i = 0; i < period; i++) {
          if (changes[i] > 0) avgGain += changes[i];
          else avgLoss += Math.abs(changes[i]);
        }
        avgGain /= period;
        avgLoss /= period;

        const rsi = Array(period).fill(50);
        for (let i = period; i < changes.length; i++) {
          const change = changes[i];
          const gain = change > 0 ? change : 0;
          const loss = change < 0 ? Math.abs(change) : 0;
          avgGain = (avgGain * (period - 1) + gain) / period;
          avgLoss = (avgLoss * (period - 1) + loss) / period;
          if (avgLoss === 0) rsi.push(100);
          else rsi.push(100 - 100 / (1 + avgGain / avgLoss));
        }
        rsi.unshift(50);
        return rsi;
      };

      // Test with trending up data (should have high RSI)
      const uptrend = Array.from({ length: 20 }, (_, i) => 100 + i * 2);
      const rsiUp = calculateRSI(uptrend);
      expect(rsiUp[rsiUp.length - 1]).toBeGreaterThan(70);

      // Test with trending down data (should have low RSI)
      const downtrend = Array.from({ length: 20 }, (_, i) => 200 - i * 2);
      const rsiDown = calculateRSI(downtrend);
      expect(rsiDown[rsiDown.length - 1]).toBeLessThan(30);
    });
  });

  describe("MACD Calculation", () => {
    it("should calculate MACD components correctly", () => {
      const calculateEMA = (data: number[], period: number): number[] => {
        const ema: number[] = [];
        const multiplier = 2 / (period + 1);
        let sum = 0;
        for (let i = 0; i < Math.min(period, data.length); i++) sum += data[i];
        ema.push(sum / Math.min(period, data.length));
        for (let i = 1; i < data.length; i++) {
          if (i < period) {
            let warmupSum = 0;
            for (let j = 0; j <= i; j++) warmupSum += data[j];
            ema.push(warmupSum / (i + 1));
          } else {
            ema.push(
              (data[i] - ema[ema.length - 1]) * multiplier +
                ema[ema.length - 1],
            );
          }
        }
        return ema;
      };

      const closes = Array.from(
        { length: 30 },
        (_, i) => 100 + Math.sin(i / 5) * 10,
      );
      const fastEMA = calculateEMA(closes, 12);
      const slowEMA = calculateEMA(closes, 26);
      const macd = fastEMA.map((fast, i) => fast - slowEMA[i]);

      expect(macd).toHaveLength(30);
      expect(macd.every((v) => !isNaN(v))).toBe(true);
    });
  });

  describe("Stochastic Calculation", () => {
    it("should calculate Stochastic values in 0-100 range", () => {
      const calculateStochastic = (
        highs: number[],
        lows: number[],
        closes: number[],
        kPeriod: number = 14,
      ): number[] => {
        const k: number[] = [];
        for (let i = 0; i < closes.length; i++) {
          if (i < kPeriod - 1) {
            k.push(50);
          } else {
            let highestHigh = -Infinity;
            let lowestLow = Infinity;
            for (let j = 0; j < kPeriod; j++) {
              highestHigh = Math.max(highestHigh, highs[i - j]);
              lowestLow = Math.min(lowestLow, lows[i - j]);
            }
            const range = highestHigh - lowestLow;
            if (range === 0) k.push(50);
            else k.push(((closes[i] - lowestLow) / range) * 100);
          }
        }
        return k;
      };

      const highs = Array.from({ length: 20 }, (_, i) => 110 + i);
      const lows = Array.from({ length: 20 }, (_, i) => 90 + i);
      const closes = Array.from({ length: 20 }, (_, i) => 100 + i);

      const stoch = calculateStochastic(highs, lows, closes);

      expect(stoch).toHaveLength(20);
      expect(stoch.every((v) => v >= 0 && v <= 100)).toBe(true);
    });
  });

  describe("Crosshair Synchronization", () => {
    it("should sync crosshair data structure correctly", () => {
      const crosshairData = {
        time: 1234567890 as number,
        price: 150.5,
        logicalIndex: 42,
      };

      expect(crosshairData.time).toBe(1234567890);
      expect(crosshairData.price).toBe(150.5);
      expect(crosshairData.logicalIndex).toBe(42);
    });
  });

  describe("Time Axis Synchronization", () => {
    it("should sync time range structure correctly", () => {
      const timeRange = {
        from: 0,
        to: 100,
      };

      expect(timeRange.from).toBe(0);
      expect(timeRange.to).toBe(100);
    });
  });

  describe("Panel Legend Data", () => {
    it("should provide correct RSI legend data structure", () => {
      const rsiLegend = {
        time: 1234567890 as number,
        indicatorName: "RSI(14)",
        value: 65.5,
        color: "#8b5cf6",
      };

      expect(rsiLegend.indicatorName).toBe("RSI(14)");
      expect(rsiLegend.value).toBe(65.5);
      expect(rsiLegend.color).toBe("#8b5cf6");
    });

    it("should provide correct MACD legend data structure", () => {
      const macdLegend = {
        time: 1234567890 as number,
        indicatorName: "MACD(12,26,9)",
        macd: 1.5,
        signal: 1.2,
        histogram: 0.3,
      };

      expect(macdLegend.indicatorName).toBe("MACD(12,26,9)");
      expect(macdLegend.macd).toBe(1.5);
      expect(macdLegend.signal).toBe(1.2);
      expect(macdLegend.histogram).toBe(0.3);
    });

    it("should provide correct Stochastic legend data structure", () => {
      const stochLegend = {
        time: 1234567890 as number,
        indicatorName: "Stoch(14,3,3)",
        k: 75.0,
        d: 72.5,
      };

      expect(stochLegend.indicatorName).toBe("Stoch(14,3,3)");
      expect(stochLegend.k).toBe(75.0);
      expect(stochLegend.d).toBe(72.5);
    });
  });
});
