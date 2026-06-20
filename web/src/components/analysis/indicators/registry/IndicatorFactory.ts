/**
 * IndicatorFactory - Factory pattern for creating indicator instances
 *
 * Maps indicator types to their corresponding classes.
 * This allows IntelligentChart to create indicators without knowing
 * the specific class implementations.
 */

import type { IndicatorConfig } from "@/contexts/AnalysisContext";
import { BaseIndicator } from "../base/BaseIndicator";
import { OverlayIndicator } from "../base/OverlayIndicator";
import { PanelIndicator } from "../base/PanelIndicator";

// Import concrete indicator classes (will be added in later phases)
// import { VolumeIndicator } from "../overlay/VolumeIndicator";
// import { SMAIndicator } from "../overlay/SMAIndicator";
// import { RSIIndicator } from "../panel/RSIIndicator";

type IndicatorConstructor = new (
  config: IndicatorConfig,
  ...args: any[]
) => BaseIndicator;

// Panel indicator order (lower = higher on screen)
const PANEL_ORDER: Record<string, number> = {
  rsi: 1,
  macd: 2,
  stoch: 3,
  adx: 4,
  atr: 5,
};

// Price scale IDs for panel indicators
const PANEL_PRICE_SCALE_IDS: Record<string, string> = {
  rsi: "rsi",
  macd: "macd",
  stoch: "stoch",
  adx: "adx",
  atr: "atr",
};

export class IndicatorFactory {
  private static registry = new Map<string, IndicatorConstructor>();

  /**
   * Register an indicator type with its constructor
   */
  static register(type: string, constructor: IndicatorConstructor): void {
    this.registry.set(type.toLowerCase(), constructor);
  }

  /**
   * Create an indicator instance from config
   */
  static create(config: IndicatorConfig): BaseIndicator | null {
    const type = config.type.toLowerCase();

    // Check if indicator is registered
    const Constructor = this.registry.get(type);
    if (!Constructor) {
      console.warn(`Indicator type "${type}" not registered in factory`);
      return null;
    }

    // Determine if overlay or panel indicator
    const isPanelIndicator = this.isPanelIndicator(type);

    if (isPanelIndicator) {
      const priceScaleId = PANEL_PRICE_SCALE_IDS[type] || type;
      const panelOrder = PANEL_ORDER[type] || 99;
      return new Constructor(
        config,
        priceScaleId,
        panelOrder,
      ) as PanelIndicator;
    } else {
      return new Constructor(config) as OverlayIndicator;
    }
  }

  /**
   * Check if indicator type is a panel indicator
   */
  private static isPanelIndicator(type: string): boolean {
    const panelTypes = ["rsi", "macd", "stoch", "stochastic", "adx", "atr"];
    return panelTypes.includes(type.toLowerCase());
  }

  /**
   * Get all registered indicator types
   */
  static getRegisteredTypes(): string[] {
    return Array.from(this.registry.keys());
  }

  /**
   * Check if indicator type is registered
   */
  static isRegistered(type: string): boolean {
    return this.registry.has(type.toLowerCase());
  }
}
