/**
 * BaseIndicator - Abstract base class for all indicators
 *
 * Implements the core interface that all indicators must provide:
 * - Calculation logic
 * - Rendering logic
 * - Strategy integration
 * - Agent integration
 * - Crosshair value extraction
 *
 * This ensures encapsulation and provides a consistent interface
 * for the IndicatorRegistry and IntelligentChartV2.
 */

import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  Time,
} from "lightweight-charts";
import type { IndicatorConfig } from "@/contexts/AnalysisContext";

// ============================================================================
// Types
// ============================================================================

export interface IndicatorData {
  time: Time;
  value: number;
}

export interface IndicatorAnalysis {
  currentValue: number | null;
  trend: "rising" | "falling" | "sideways" | null;
  signal: "buy" | "sell" | "neutral" | null;
  strength: number; // 0-100
  interpretation: string; // Human-readable analysis
}

export interface Signal {
  timestamp: number;
  type: "buy" | "sell" | "warning";
  strength: number; // 0-100
  indicator: string;
  description: string;
}

export interface IndicatorContext {
  name: string;
  type: string;
  params: Record<string, number | string>;
  currentValue: number | null;
  analysis?: IndicatorAnalysis;
  recentAnalysis?: IndicatorAnalysis[];
  signals?: Signal[];
}

// ============================================================================
// Abstract Base Class
// ============================================================================

export abstract class BaseIndicator {
  protected config: IndicatorConfig;
  protected chart: IChartApi | null = null;
  protected series: ISeriesApi<any> | Map<string, ISeriesApi<any>> | null =
    null;
  protected data: IndicatorData[] = [];

  constructor(config: IndicatorConfig) {
    this.config = config;
  }

  // ========================================================================
  // Core Interface (Must be implemented by subclasses)
  // ========================================================================

  /**
   * Calculate indicator values from candle data
   * Must be implemented by each indicator
   */
  abstract calculate(candleData: CandlestickData<Time>[]): IndicatorData[];

  /**
   * Render indicator on chart
   * Must be implemented by each indicator
   */
  abstract render(chart: IChartApi, data: IndicatorData[]): void;

  /**
   * Clean up indicator (remove series, etc.)
   * Must be implemented by each indicator
   */
  abstract cleanup(chart: IChartApi): void;

  // ========================================================================
  // Strategy Integration (Must be implemented by subclasses)
  // ========================================================================

  /**
   * Get field names available for strategy rules
   * e.g., ["rsi_14"] for RSI, ["macd_line", "macd_signal", "macd_hist"] for MACD
   */
  abstract getStrategyFields(): string[];

  // ========================================================================
  // Agent Integration (Must be implemented by subclasses)
  // ========================================================================

  /**
   * Get context for agent awareness
   * Includes current value, state, signals, etc.
   */
  abstract getAgentContext(): IndicatorContext;

  /**
   * Get current analysis (trend, signal, strength, interpretation)
   * Used by agent for comprehensive chart analysis
   */
  getCurrentAnalysis(): IndicatorAnalysis {
    const currentValue = this.getCurrentValue();
    if (currentValue === null) {
      return {
        currentValue: null,
        trend: null,
        signal: "neutral",
        strength: 0,
        interpretation: "Insufficient data",
      };
    }

    // Default implementation - subclasses can override
    return {
      currentValue,
      trend: this.getTrend(),
      signal: "neutral",
      strength: 50,
      interpretation: `${this.config.name}: ${currentValue.toFixed(2)}`,
    };
  }

  /**
   * Get recent analysis for trend detection
   * Returns analysis for last N periods
   */
  getRecentAnalysis(count: number = 10): IndicatorAnalysis[] {
    if (this.data.length === 0) return [];

    const recent = this.data.slice(-count);
    return recent.map((point) => ({
      currentValue: point.value,
      trend: null, // Would need historical comparison
      signal: "neutral",
      strength: 50,
      interpretation: `${this.config.name}: ${point.value.toFixed(2)}`,
    }));
  }

  /**
   * Detect signals (crossovers, breakouts, reversals, etc.)
   * Subclasses should override to provide indicator-specific signals
   */
  detectSignals(): Signal[] {
    // Default: no signals
    // Subclasses should implement signal detection logic
    return [];
  }

  // ========================================================================
  // Crosshair Integration
  // ========================================================================

  /**
   * Get indicator value at specific timestamp
   * Used for crosshair display
   */
  getCrosshairValue(timestamp: number): number | null {
    if (this.data.length === 0) return null;

    // Find closest data point to timestamp
    let closest = this.data[0];
    let minDiff = Math.abs((this.data[0].time as number) - timestamp);

    for (const point of this.data) {
      const diff = Math.abs((point.time as number) - timestamp);
      if (diff < minDiff) {
        minDiff = diff;
        closest = point;
      }
    }

    // Only return if within 1 day (86400 seconds) of target
    return minDiff < 86400 ? closest.value : null;
  }

  // ========================================================================
  // Helper Methods
  // ========================================================================

  /**
   * Get current (latest) indicator value
   */
  getCurrentValue(): number | null {
    if (this.data.length === 0) return null;
    return this.data[this.data.length - 1].value;
  }

  /**
   * Get trend direction (rising, falling, sideways)
   * Default implementation - subclasses can override
   */
  protected getTrend(): "rising" | "falling" | "sideways" | null {
    if (this.data.length < 2) return null;

    const recent = this.data.slice(-5); // Last 5 points
    if (recent.length < 2) return null;

    const first = recent[0].value;
    const last = recent[recent.length - 1].value;
    const diff = last - first;
    const threshold = Math.abs(first * 0.01); // 1% threshold

    if (diff > threshold) return "rising";
    if (diff < -threshold) return "falling";
    return "sideways";
  }

  /**
   * Get indicator name
   */
  getName(): string {
    return this.config.name;
  }

  /**
   * Get indicator type
   */
  getType(): string {
    return this.config.type;
  }

  /**
   * Check if indicator is visible
   */
  isVisible(): boolean {
    return this.config.visible;
  }

  /**
   * Update indicator data
   */
  updateData(data: IndicatorData[]): void {
    this.data = data;
  }

  /**
   * Get stored indicator data
   */
  getData(): IndicatorData[] {
    return this.data;
  }
}
