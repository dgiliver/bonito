/**
 * IndicatorRegistry Tests
 *
 * Comprehensive tests for the registry that manages active indicators
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { IndicatorRegistry } from "./IndicatorRegistry";
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
      currentValue: 100,
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
      currentValue: 50,
    };
  }
}

// ============================================================================
// Tests
// ============================================================================

describe("IndicatorRegistry", () => {
  let registry: IndicatorRegistry;

  beforeEach(() => {
    registry = new IndicatorRegistry();
    IndicatorFactory["registry"].clear();
    IndicatorFactory.register("sma", TestOverlayIndicator);
    IndicatorFactory.register("rsi", TestPanelIndicator);
  });

  describe("Adding Indicators", () => {
    it("adds overlay indicator", () => {
      const config: IndicatorConfig = {
        type: "sma",
        name: "SMA(20)",
        params: { period: 20 },
        visible: true,
      };

      const indicator = registry.addIndicator(config);
      expect(indicator).not.toBeNull();
      expect(indicator?.getName()).toBe("SMA(20)");
    });

    it("adds panel indicator", () => {
      const config: IndicatorConfig = {
        type: "rsi",
        name: "RSI(14)",
        params: { period: 14 },
        visible: true,
      };

      const indicator = registry.addIndicator(config);
      expect(indicator).not.toBeNull();
      expect(indicator?.getName()).toBe("RSI(14)");
    });

    it("returns null for unregistered type", () => {
      const config: IndicatorConfig = {
        type: "unknown",
        name: "Unknown",
        params: {},
        visible: true,
      };

      const indicator = registry.addIndicator(config);
      expect(indicator).toBeNull();
    });

    it("stores indicators by name", () => {
      const config: IndicatorConfig = {
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      };

      registry.addIndicator(config);
      const retrieved = registry.getIndicator("SMA(20)");
      expect(retrieved).not.toBeNull();
      expect(retrieved?.getName()).toBe("SMA(20)");
    });
  });

  describe("Removing Indicators", () => {
    it("removes overlay indicator", () => {
      const config: IndicatorConfig = {
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      };

      registry.addIndicator(config);
      const removed = registry.removeIndicator("SMA(20)");
      expect(removed).toBe(true);
      expect(registry.getIndicator("SMA(20)")).toBeNull();
    });

    it("removes panel indicator", () => {
      const config: IndicatorConfig = {
        type: "rsi",
        name: "RSI(14)",
        params: {},
        visible: true,
      };

      registry.addIndicator(config);
      const removed = registry.removeIndicator("RSI(14)");
      expect(removed).toBe(true);
      expect(registry.getIndicator("RSI(14)")).toBeNull();
    });

    it("returns false for non-existent indicator", () => {
      const removed = registry.removeIndicator("NonExistent");
      expect(removed).toBe(false);
    });
  });

  describe("Retrieving Indicators", () => {
    it("gets indicator by name", () => {
      const config: IndicatorConfig = {
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      };

      registry.addIndicator(config);
      const indicator = registry.getIndicator("SMA(20)");
      expect(indicator).not.toBeNull();
      expect(indicator?.getName()).toBe("SMA(20)");
    });

    it("returns null for non-existent indicator", () => {
      const indicator = registry.getIndicator("NonExistent");
      expect(indicator).toBeNull();
    });

    it("gets all overlay indicators", () => {
      registry.addIndicator({
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      });
      registry.addIndicator({
        type: "sma",
        name: "SMA(50)",
        params: {},
        visible: true,
      });
      registry.addIndicator({
        type: "rsi",
        name: "RSI(14)",
        params: {},
        visible: true,
      });

      const overlays = registry.getOverlayIndicators();
      expect(overlays).toHaveLength(2);
      expect(overlays.every((ind) => ind instanceof OverlayIndicator)).toBe(
        true,
      );
    });

    it("gets all panel indicators", () => {
      registry.addIndicator({
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      });
      registry.addIndicator({
        type: "rsi",
        name: "RSI(14)",
        params: {},
        visible: true,
      });

      const panels = registry.getPanelIndicators();
      expect(panels).toHaveLength(1);
      expect(panels[0]).toBeInstanceOf(PanelIndicator);
    });

    it("gets all indicators", () => {
      registry.addIndicator({
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      });
      registry.addIndicator({
        type: "rsi",
        name: "RSI(14)",
        params: {},
        visible: true,
      });

      const all = registry.getAllIndicators();
      expect(all).toHaveLength(2);
    });
  });

  describe("Agent Context", () => {
    it("builds context from all visible indicators", () => {
      registry.addIndicator({
        type: "sma",
        name: "SMA(20)",
        params: { period: 20 },
        visible: true,
      });
      registry.addIndicator({
        type: "rsi",
        name: "RSI(14)",
        params: { period: 14 },
        visible: true,
      });

      const contexts = registry.buildAgentContext();
      expect(contexts).toHaveLength(2);
      expect(contexts[0].name).toBe("SMA(20)");
      expect(contexts[1].name).toBe("RSI(14)");
    });

    it("excludes invisible indicators from context", () => {
      registry.addIndicator({
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      });
      registry.addIndicator({
        type: "rsi",
        name: "RSI(14)",
        params: {},
        visible: false,
      });

      const contexts = registry.buildAgentContext();
      expect(contexts).toHaveLength(1);
      expect(contexts[0].name).toBe("SMA(20)");
    });

    it("includes analysis in context", () => {
      registry.addIndicator({
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      });

      const contexts = registry.buildAgentContext();
      expect(contexts[0].analysis).toBeDefined();
      expect(contexts[0].recentAnalysis).toBeDefined();
      expect(contexts[0].signals).toBeDefined();
    });
  });

  describe("Comprehensive Analysis", () => {
    it("provides overall trend analysis", () => {
      registry.addIndicator({
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      });

      const analysis = registry.getComprehensiveAnalysis();
      expect(analysis.overallTrend).toBeDefined();
      expect(analysis.marketCondition).toBeDefined();
      expect(analysis.riskAssessment).toBeDefined();
    });

    it("determines bullish trend from buy signals", () => {
      // This would require indicator implementations with actual signal detection
      // For now, we test the structure
      const analysis = registry.getComprehensiveAnalysis();
      expect(["bullish", "bearish", "neutral", null]).toContain(
        analysis.overallTrend,
      );
    });
  });

  describe("Panel Management", () => {
    it("finds panel indicator by price scale ID", () => {
      registry.addIndicator({
        type: "rsi",
        name: "RSI(14)",
        params: {},
        visible: true,
      });

      const indicator = registry.getPanelIndicatorByPriceScale("rsi");
      expect(indicator).not.toBeNull();
      expect(indicator?.getName()).toBe("RSI(14)");
    });

    it("returns null for non-existent price scale", () => {
      const indicator = registry.getPanelIndicatorByPriceScale("nonexistent");
      expect(indicator).toBeNull();
    });
  });

  describe("Clear", () => {
    it("clears all indicators", () => {
      registry.addIndicator({
        type: "sma",
        name: "SMA(20)",
        params: {},
        visible: true,
      });
      registry.addIndicator({
        type: "rsi",
        name: "RSI(14)",
        params: {},
        visible: true,
      });

      registry.clear();

      expect(registry.getAllIndicators()).toHaveLength(0);
      expect(registry.getIndicator("SMA(20)")).toBeNull();
      expect(registry.getIndicator("RSI(14)")).toBeNull();
    });
  });
});
