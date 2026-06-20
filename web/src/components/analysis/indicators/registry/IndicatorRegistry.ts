/**
 * IndicatorRegistry - Manages active indicators and provides unified interface
 *
 * Responsibilities:
 * - Track active indicators (overlays and panels)
 * - Provide factory interface for creating indicators
 * - Aggregate indicator context for agent
 * - Manage indicator lifecycle (add, remove, update)
 * - Provide comprehensive chart analysis
 */

import type { IndicatorConfig } from "@/contexts/AnalysisContext";
import type {
  BaseIndicator,
  IndicatorContext,
  IndicatorAnalysis,
} from "../base/BaseIndicator";
import { IndicatorFactory } from "./IndicatorFactory";

export class IndicatorRegistry {
  private overlayIndicators = new Map<string, BaseIndicator>();
  private panelIndicators = new Map<string, BaseIndicator>();

  /**
   * Add or update an indicator
   */
  addIndicator(config: IndicatorConfig): BaseIndicator | null {
    const indicator = IndicatorFactory.create(config);
    if (!indicator) return null;

    // Determine if overlay or panel
    const isPanel = this.isPanelIndicator(config.type);

    if (isPanel) {
      this.panelIndicators.set(config.name, indicator);
    } else {
      this.overlayIndicators.set(config.name, indicator);
    }

    return indicator;
  }

  /**
   * Remove an indicator
   */
  removeIndicator(name: string): boolean {
    const removedOverlay = this.overlayIndicators.delete(name);
    const removedPanel = this.panelIndicators.delete(name);
    return removedOverlay || removedPanel;
  }

  /**
   * Get indicator by name
   */
  getIndicator(name: string): BaseIndicator | null {
    return (
      this.overlayIndicators.get(name) || this.panelIndicators.get(name) || null
    );
  }

  /**
   * Get all overlay indicators
   */
  getOverlayIndicators(): BaseIndicator[] {
    return Array.from(this.overlayIndicators.values());
  }

  /**
   * Get all panel indicators (sorted by panel order)
   */
  getPanelIndicators(): BaseIndicator[] {
    const panels = Array.from(this.panelIndicators.values());
    // Sort by panel order (will be implemented when PanelIndicator is fully set up)
    return panels;
  }

  /**
   * Get all active indicators
   */
  getAllIndicators(): BaseIndicator[] {
    return [...this.getOverlayIndicators(), ...this.getPanelIndicators()];
  }

  /**
   * Get panel indicator by price scale ID
   */
  getPanelIndicatorByPriceScale(priceScaleId: string): BaseIndicator | null {
    for (const indicator of this.panelIndicators.values()) {
      // Check if indicator has this price scale ID
      // This will be implemented when PanelIndicator methods are available
      if ("getPriceScaleId" in indicator) {
        const scaleId = (indicator as any).getPriceScaleId();
        if (scaleId === priceScaleId) {
          return indicator;
        }
      }
    }
    return null;
  }

  /**
   * Build agent context from all active indicators
   */
  buildAgentContext(): IndicatorContext[] {
    return this.getAllIndicators()
      .filter((ind) => ind.isVisible())
      .map((ind) => ({
        ...ind.getAgentContext(),
        analysis: ind.getCurrentAnalysis(),
        recentAnalysis: ind.getRecentAnalysis(10),
        signals: ind.detectSignals(),
      }));
  }

  /**
   * Get comprehensive chart analysis
   */
  getComprehensiveAnalysis(): {
    indicators: IndicatorContext[];
    overallTrend: "bullish" | "bearish" | "neutral" | null;
    marketCondition: "trending" | "ranging" | "volatile" | null;
    keyLevels: Array<{ price: number; type: "support" | "resistance" }>;
    riskAssessment: "low" | "medium" | "high" | null;
  } {
    const indicators = this.buildAgentContext();

    // Determine overall trend from indicators
    const overallTrend = this.determineOverallTrend(indicators);

    // Determine market condition
    const marketCondition = this.determineMarketCondition(indicators);

    // Detect key levels (simplified - would need price data)
    const keyLevels: Array<{ price: number; type: "support" | "resistance" }> =
      [];

    // Assess risk
    const riskAssessment = this.assessRisk(indicators);

    return {
      indicators,
      overallTrend,
      marketCondition,
      keyLevels,
      riskAssessment,
    };
  }

  /**
   * Determine overall trend from indicators
   */
  private determineOverallTrend(
    indicators: IndicatorContext[],
  ): "bullish" | "bearish" | "neutral" | null {
    if (indicators.length === 0) return null;

    let bullishCount = 0;
    let bearishCount = 0;

    for (const ind of indicators) {
      const analysis = ind.analysis;
      if (!analysis) continue;

      if (analysis.signal === "buy") bullishCount++;
      if (analysis.signal === "sell") bearishCount++;
    }

    if (bullishCount > bearishCount) return "bullish";
    if (bearishCount > bullishCount) return "bearish";
    return "neutral";
  }

  /**
   * Determine market condition
   */
  private determineMarketCondition(
    indicators: IndicatorContext[],
  ): "trending" | "ranging" | "volatile" | null {
    if (indicators.length === 0) return null;

    // Check for ADX (trend strength indicator)
    const adx = indicators.find((ind) => ind.type.toLowerCase() === "adx");
    if (adx && adx.currentValue !== null) {
      if (adx.currentValue > 25) return "trending";
      if (adx.currentValue < 20) return "ranging";
    }

    // Check for ATR (volatility indicator)
    const atr = indicators.find((ind) => ind.type.toLowerCase() === "atr");
    if (atr && atr.currentValue !== null) {
      // High ATR = volatile (would need historical comparison for accurate assessment)
      return "volatile";
    }

    return "trending"; // Default
  }

  /**
   * Assess risk level
   */
  private assessRisk(
    indicators: IndicatorContext[],
  ): "low" | "medium" | "high" | null {
    if (indicators.length === 0) return null;

    // Check for conflicting signals
    const signals = indicators.flatMap((ind) => ind.signals || []);
    const buySignals = signals.filter((s) => s.type === "buy").length;
    const sellSignals = signals.filter((s) => s.type === "sell").length;

    // Conflicting signals = higher risk
    if (buySignals > 0 && sellSignals > 0) return "high";

    // Check RSI for overbought/oversold
    const rsi = indicators.find((ind) => ind.type.toLowerCase() === "rsi");
    if (rsi && rsi.currentValue !== null) {
      if (rsi.currentValue > 80 || rsi.currentValue < 20) return "high";
    }

    return "medium"; // Default
  }

  /**
   * Get indicator relationships (for correlation analysis)
   */
  getIndicatorRelationships(indicator: BaseIndicator): IndicatorContext[] {
    // Simplified - would need correlation calculation
    // For now, return other indicators of different types
    return this.getAllIndicators()
      .filter((ind) => ind.getName() !== indicator.getName())
      .map((ind) => ind.getAgentContext());
  }

  /**
   * Clear all indicators
   */
  clear(): void {
    this.overlayIndicators.clear();
    this.panelIndicators.clear();
  }

  /**
   * Check if indicator type is a panel indicator
   */
  private isPanelIndicator(type: string): boolean {
    const panelTypes = ["rsi", "macd", "stoch", "stochastic", "adx", "atr"];
    return panelTypes.includes(type.toLowerCase());
  }
}
