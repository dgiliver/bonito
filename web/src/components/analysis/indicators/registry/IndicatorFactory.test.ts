/**
 * IndicatorFactory Tests
 *
 * Tests for the factory pattern that creates indicator instances
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import IndicatorFactory from "./IndicatorFactory";
import { OverlayIndicator } from "../base/OverlayIndicator";
import { PanelIndicator } from "../base/PanelIndicator";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";
import type { CandlestickData, Time } from "lightweight-charts";

// ============================================================================
// Test Implementations
// ============================================================================

class TestOverlayIndicator extends OverlayIndicator {
  calculate() {
    return [];
  }
  getStrategyFields() {
    return ["test_overlay"];
  }
  getAgentContext() {
    return {
      name: this.config.name,
      type: this.config.type,
      params: this.config.params,
      currentValue: null,
    };
  }
}

class TestPanelIndicator extends PanelIndicator {
  calculate() {
    return [];
  }
  getStrategyFields() {
    return ["test_panel"];
  }
  getAgentContext() {
    return {
      name: this.config.name,
      type: this.config.type,
      params: this.config.params,
      currentValue: null,
    };
  }
}

// ============================================================================
// Tests
// ============================================================================

describe("IndicatorFactory", () => {
  beforeEach(() => {
    // Clear registry before each test
    IndicatorFactory["registry"].clear();
  });

  describe("Registration", () => {
    it("registers indicator type", () => {
      IndicatorFactory.register("test_overlay", TestOverlayIndicator);
      expect(IndicatorFactory.isRegistered("test_overlay")).toBe(true);
    });

    it("registers case-insensitively", () => {
      IndicatorFactory.register("TEST_OVERLAY", TestOverlayIndicator);
      expect(IndicatorFactory.isRegistered("test_overlay")).toBe(true);
      expect(IndicatorFactory.isRegistered("TEST_OVERLAY")).toBe(true);
    });

    it("allows multiple registrations", () => {
      IndicatorFactory.register("sma", TestOverlayIndicator);
      IndicatorFactory.register("ema", TestOverlayIndicator);
      IndicatorFactory.register("rsi", TestPanelIndicator);

      expect(IndicatorFactory.isRegistered("sma")).toBe(true);
      expect(IndicatorFactory.isRegistered("ema")).toBe(true);
      expect(IndicatorFactory.isRegistered("rsi")).toBe(true);
    });

    it("overwrites existing registration", () => {
      IndicatorFactory.register("test", TestOverlayIndicator);
      IndicatorFactory.register("test", TestPanelIndicator);

      const indicator = IndicatorFactory.create({
        type: "test",
        name: "Test",
        params: {},
        visible: true,
      });

      expect(indicator).toBeInstanceOf(PanelIndicator);
    });
  });

  describe("Creation", () => {
    it("creates overlay indicator for overlay types", () => {
      IndicatorFactory.register("sma", TestOverlayIndicator);
      const config: IndicatorConfig = {
        type: "sma",
        name: "SMA(20)",
        params: { period: 20 },
        visible: true,
      };

      const indicator = IndicatorFactory.create(config);
      expect(indicator).toBeInstanceOf(OverlayIndicator);
      expect(indicator).toBeInstanceOf(TestOverlayIndicator);
    });

    it("creates panel indicator for panel types", () => {
      IndicatorFactory.register("rsi", TestPanelIndicator);
      const config: IndicatorConfig = {
        type: "rsi",
        name: "RSI(14)",
        params: { period: 14 },
        visible: true,
      };

      const indicator = IndicatorFactory.create(config);
      expect(indicator).toBeInstanceOf(PanelIndicator);
      expect(indicator).toBeInstanceOf(TestPanelIndicator);
    });

    it("returns null for unregistered type", () => {
      const config: IndicatorConfig = {
        type: "unknown",
        name: "Unknown",
        params: {},
        visible: true,
      };

      const indicator = IndicatorFactory.create(config);
      expect(indicator).toBeNull();
    });

    it("passes config to constructor", () => {
      IndicatorFactory.register("sma", TestOverlayIndicator);
      const config: IndicatorConfig = {
        type: "sma",
        name: "SMA(20)",
        params: { period: 20 },
        visible: true,
      };

      const indicator = IndicatorFactory.create(config);
      expect(indicator?.getName()).toBe("SMA(20)");
      expect(indicator?.getType()).toBe("sma");
    });

    it("creates panel indicator with price scale ID and order", () => {
      IndicatorFactory.register("rsi", TestPanelIndicator);
      const config: IndicatorConfig = {
        type: "rsi",
        name: "RSI(14)",
        params: { period: 14 },
        visible: true,
      };

      const indicator = IndicatorFactory.create(config) as PanelIndicator;
      expect(indicator.getPriceScaleId()).toBe("rsi");
      expect(indicator.getPanelOrder()).toBe(1); // From PANEL_ORDER map
    });

    it("handles case-insensitive type lookup", () => {
      IndicatorFactory.register("sma", TestOverlayIndicator);
      const config: IndicatorConfig = {
        type: "SMA",
        name: "SMA(20)",
        params: {},
        visible: true,
      };

      const indicator = IndicatorFactory.create(config);
      expect(indicator).not.toBeNull();
    });
  });

  describe("Panel Detection", () => {
    it("identifies RSI as panel indicator", () => {
      IndicatorFactory.register("rsi", TestPanelIndicator);
      const config: IndicatorConfig = {
        type: "rsi",
        name: "RSI(14)",
        params: {},
        visible: true,
      };

      const indicator = IndicatorFactory.create(config);
      expect(indicator).toBeInstanceOf(PanelIndicator);
    });

    it("identifies MACD as panel indicator", () => {
      IndicatorFactory.register("macd", TestPanelIndicator);
      const config: IndicatorConfig = {
        type: "macd",
        name: "MACD",
        params: {},
        visible: true,
      };

      const indicator = IndicatorFactory.create(config);
      expect(indicator).toBeInstanceOf(PanelIndicator);
    });

    it("identifies SMA as overlay indicator", () => {
      IndicatorFactory.register("sma", TestOverlayIndicator);
      const config: IndicatorConfig = {
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      };

      const indicator = IndicatorFactory.create(config);
      expect(indicator).toBeInstanceOf(OverlayIndicator);
      expect(indicator).not.toBeInstanceOf(PanelIndicator);
    });
  });

  describe("Registry Management", () => {
    it("returns all registered types", () => {
      IndicatorFactory.register("sma", TestOverlayIndicator);
      IndicatorFactory.register("ema", TestOverlayIndicator);
      IndicatorFactory.register("rsi", TestPanelIndicator);

      const types = IndicatorFactory.getRegisteredTypes();
      expect(types).toContain("sma");
      expect(types).toContain("ema");
      expect(types).toContain("rsi");
    });

    it("returns empty array when no types registered", () => {
      const types = IndicatorFactory.getRegisteredTypes();
      expect(types).toEqual([]);
    });

    it("checks registration status correctly", () => {
      expect(IndicatorFactory.isRegistered("sma")).toBe(false);
      IndicatorFactory.register("sma", TestOverlayIndicator);
      expect(IndicatorFactory.isRegistered("sma")).toBe(true);
    });
  });
});
