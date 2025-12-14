/**
 * registerIndicators - Initialize indicator factory with all available indicators
 *
 * This should be called once at app startup to register all indicator types
 */

import IndicatorFactory from "./IndicatorFactory";
import {
  SMAIndicator,
  EMAIndicator,
  BollingerBandsIndicator,
} from "../overlay";
import { RSIIndicator } from "../panel";

export function registerIndicators(): void {
  // Overlay indicators
  IndicatorFactory.register("sma", SMAIndicator);
  IndicatorFactory.register("ema", EMAIndicator);
  IndicatorFactory.register("bbands", BollingerBandsIndicator);
  IndicatorFactory.register("bollinger", BollingerBandsIndicator); // Alias

  // Panel indicators
  IndicatorFactory.register("rsi", RSIIndicator);
}

// Auto-register on import (for convenience)
registerIndicators();
