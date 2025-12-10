"use client";

/**
 * AnalysisContext - Shared state for Agent-Chart Synthesis
 *
 * ⚠️ INTEGRATION RULES: See docs/AGENT_CHART_SYNTHESIS.md
 *
 * This context is the SINGLE SOURCE OF TRUTH for:
 * - Chart state (symbol, interval, range, indicators)
 * - Backtest results and selected trade
 * - Strategy configuration
 * - Agent intents (commands from agent → chart)
 * - Annotations and drawings
 *
 * When adding new chart features:
 * 1. Add state shape to AnalysisState
 * 2. Add action types to AnalysisAction
 * 3. Update ChartContextPayload for agent awareness
 * 4. Add ChartIntent type for agent control
 *
 * NEVER create parallel state in components for shared concerns.
 */

import React, { createContext, useContext, useReducer, useCallback, ReactNode } from "react";

// ============================================================================
// Types
// ============================================================================

export interface IndicatorConfig {
  type: string;
  name: string;
  params: Record<string, number | string>;
  visible: boolean;
}

export interface Trade {
  id: string;
  entry_time: string;
  exit_time: string;
  side: "long" | "short";
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  pnl_percent: number;
  exit_reason: string;
}

export interface BacktestResult {
  strategy_name: string;
  symbol: string;
  period: { start: string; end: string };
  performance: {
    total_return: number;
    sharpe_ratio: number;
    max_drawdown: number;
    win_rate: number;
    buy_hold_return?: number;
    alpha?: number;
  };
  trades: Trade[];
  equity_curve: { date: string; equity: number }[];
}

export interface StrategyConfig {
  name: string;
  description: string;
  indicators: IndicatorConfig[];
  entry_rules: unknown[];
  exit_rules: unknown[];
}

export interface Annotation {
  id: string;
  type: "marker" | "line" | "label" | "region";
  timestamp: number;
  text?: string;
  color?: string;
  icon?: "entry" | "exit" | "stop" | "signal" | "warning" | "info";
  endTimestamp?: number; // For regions
  price?: number; // For price-level annotations
}

export interface ChartIntent {
  id: string;
  type: "navigate" | "annotate" | "overlay" | "highlight" | "clear";
  processed: boolean;

  // Navigation
  timestamp?: number;
  range?: { start: number; end: number };

  // Annotation
  annotation?: Omit<Annotation, "id">;

  // Overlay
  indicator?: IndicatorConfig;

  // Highlight
  highlightRange?: { start: number; end: number; color: string };

  // Clear
  clearType?: "annotations" | "indicators" | "highlights" | "all";
}

export interface ChartEvent {
  type: "click" | "select" | "hover" | "range_change";
  timestamp?: number;
  price?: number;
  target?: {
    type: "candle" | "marker" | "indicator" | "annotation" | "trade";
    data?: unknown;
    tradeId?: string;
  };
  visibleRange?: { start: number; end: number };
}

export interface ChartState {
  symbol: string;
  interval: string;
  visibleRange: { start: number; end: number } | null;
  indicators: IndicatorConfig[];
  cursorPosition: { timestamp: number; price: number } | null;
}

export interface AnalysisState {
  // Chart state
  chart: ChartState;

  // Active strategy
  strategy: StrategyConfig | null;

  // Backtest results
  backtest: {
    result: BacktestResult | null;
    selectedTrade: Trade | null;
  };

  // Annotations from agent
  annotations: Annotation[];

  // Agent intents queue (processed by chart)
  pendingIntents: ChartIntent[];

  // UI state
  ui: {
    showTradeMarkers: boolean;
    showAnnotations: boolean;
    sidePanel: "chat" | "trade-details" | "strategy-info" | null;
  };
}

// ============================================================================
// Actions
// ============================================================================

type AnalysisAction =
  // Chart actions
  | { type: "SET_SYMBOL"; symbol: string }
  | { type: "SET_INTERVAL"; interval: string }
  | { type: "SET_VISIBLE_RANGE"; range: { start: number; end: number } }
  | { type: "SET_CURSOR"; position: { timestamp: number; price: number } | null }
  | { type: "ADD_INDICATOR"; indicator: IndicatorConfig }
  | { type: "REMOVE_INDICATOR"; name: string }
  | { type: "TOGGLE_INDICATOR"; name: string }

  // Strategy actions
  | { type: "SET_STRATEGY"; strategy: StrategyConfig | null }

  // Backtest actions
  | { type: "SET_BACKTEST_RESULT"; result: BacktestResult | null }
  | { type: "SELECT_TRADE"; trade: Trade | null }

  // Annotation actions
  | { type: "ADD_ANNOTATION"; annotation: Annotation }
  | { type: "REMOVE_ANNOTATION"; id: string }
  | { type: "CLEAR_ANNOTATIONS" }

  // Intent actions (from agent)
  | { type: "ADD_INTENT"; intent: Omit<ChartIntent, "id" | "processed"> }
  | { type: "PROCESS_INTENT"; intentId: string }
  | { type: "CLEAR_INTENTS" }

  // UI actions
  | { type: "SET_SIDE_PANEL"; panel: AnalysisState["ui"]["sidePanel"] }
  | { type: "TOGGLE_TRADE_MARKERS"; show: boolean }
  | { type: "TOGGLE_ANNOTATIONS"; show: boolean }

  // Chart events (from chart component)
  | { type: "CHART_EVENT"; event: ChartEvent };

// ============================================================================
// Initial State
// ============================================================================

const initialState: AnalysisState = {
  chart: {
    symbol: "SPY",
    interval: "1d",
    visibleRange: null,
    indicators: [],
    cursorPosition: null,
  },
  strategy: null,
  backtest: {
    result: null,
    selectedTrade: null,
  },
  annotations: [],
  pendingIntents: [],
  ui: {
    showTradeMarkers: true,
    showAnnotations: true,
    sidePanel: "chat",
  },
};

// ============================================================================
// Reducer
// ============================================================================

function analysisReducer(state: AnalysisState, action: AnalysisAction): AnalysisState {
  switch (action.type) {
    // Chart actions
    case "SET_SYMBOL": {
      // Only clear backtest if switching to a DIFFERENT symbol than the backtest
      // (Don't clear when syncing to backtest symbol)
      const backtestSymbol = state.backtest.result?.symbol;
      const shouldClearBacktest = backtestSymbol && backtestSymbol !== action.symbol;

      return {
        ...state,
        chart: { ...state.chart, symbol: action.symbol },
        backtest: shouldClearBacktest
          ? { result: null, selectedTrade: null }
          : state.backtest,
        annotations: shouldClearBacktest ? [] : state.annotations,
      };
    }

    case "SET_INTERVAL":
      return {
        ...state,
        chart: { ...state.chart, interval: action.interval },
      };

    case "SET_VISIBLE_RANGE":
      return {
        ...state,
        chart: { ...state.chart, visibleRange: action.range },
      };

    case "SET_CURSOR":
      return {
        ...state,
        chart: { ...state.chart, cursorPosition: action.position },
      };

    case "ADD_INDICATOR": {
      const exists = state.chart.indicators.some(i => i.name === action.indicator.name);
      if (exists) return state;
      return {
        ...state,
        chart: {
          ...state.chart,
          indicators: [...state.chart.indicators, action.indicator],
        },
      };
    }

    case "REMOVE_INDICATOR":
      return {
        ...state,
        chart: {
          ...state.chart,
          indicators: state.chart.indicators.filter(i => i.name !== action.name),
        },
      };

    case "TOGGLE_INDICATOR":
      return {
        ...state,
        chart: {
          ...state.chart,
          indicators: state.chart.indicators.map(i =>
            i.name === action.name ? { ...i, visible: !i.visible } : i
          ),
        },
      };

    // Strategy actions
    case "SET_STRATEGY":
      return {
        ...state,
        strategy: action.strategy,
        // Auto-add strategy indicators to chart
        chart: action.strategy ? {
          ...state.chart,
          indicators: action.strategy.indicators.map(i => ({ ...i, visible: true })),
        } : state.chart,
      };

    // Backtest actions
    case "SET_BACKTEST_RESULT":
      return {
        ...state,
        backtest: {
          result: action.result,
          selectedTrade: null,
        },
        // Keep current panel - only switch to trade-details when user clicks a trade
        ui: state.ui,
      };

    case "SELECT_TRADE":
      return {
        ...state,
        backtest: {
          ...state.backtest,
          selectedTrade: action.trade,
        },
        ui: {
          ...state.ui,
          sidePanel: action.trade ? "trade-details" : state.ui.sidePanel,
        },
      };

    // Annotation actions
    case "ADD_ANNOTATION":
      return {
        ...state,
        annotations: [...state.annotations, action.annotation],
      };

    case "REMOVE_ANNOTATION":
      return {
        ...state,
        annotations: state.annotations.filter(a => a.id !== action.id),
      };

    case "CLEAR_ANNOTATIONS":
      return {
        ...state,
        annotations: [],
      };

    // Intent actions
    case "ADD_INTENT": {
      const intent: ChartIntent = {
        ...action.intent,
        id: crypto.randomUUID(),
        processed: false,
      };
      return {
        ...state,
        pendingIntents: [...state.pendingIntents, intent],
      };
    }

    case "PROCESS_INTENT":
      return {
        ...state,
        pendingIntents: state.pendingIntents.map(i =>
          i.id === action.intentId ? { ...i, processed: true } : i
        ).filter(i => !i.processed),
      };

    case "CLEAR_INTENTS":
      return {
        ...state,
        pendingIntents: [],
      };

    // UI actions
    case "SET_SIDE_PANEL":
      return {
        ...state,
        ui: { ...state.ui, sidePanel: action.panel },
      };

    case "TOGGLE_TRADE_MARKERS":
      return {
        ...state,
        ui: { ...state.ui, showTradeMarkers: action.show },
      };

    case "TOGGLE_ANNOTATIONS":
      return {
        ...state,
        ui: { ...state.ui, showAnnotations: action.show },
      };

    // Chart events
    case "CHART_EVENT": {
      const event = action.event;

      // Handle trade selection from chart click
      if (event.type === "click" && event.target?.type === "trade" && event.target.tradeId) {
        const trade = state.backtest.result?.trades.find(
          t => t.id === event.target?.tradeId
        );
        if (trade) {
          return {
            ...state,
            backtest: { ...state.backtest, selectedTrade: trade },
            ui: { ...state.ui, sidePanel: "trade-details" },
          };
        }
      }

      // Handle range change
      if (event.type === "range_change" && event.visibleRange) {
        return {
          ...state,
          chart: { ...state.chart, visibleRange: event.visibleRange },
        };
      }

      return state;
    }

    default:
      return state;
  }
}

// ============================================================================
// Context
// ============================================================================

interface AnalysisContextValue {
  state: AnalysisState;
  dispatch: React.Dispatch<AnalysisAction>;

  // Convenience methods
  getChartContext: () => ChartContextPayload;
  emitChartEvent: (event: ChartEvent) => void;
  addAgentIntent: (intent: Omit<ChartIntent, "id" | "processed">) => void;
}

// What we send to the agent
export interface ChartContextPayload {
  symbol: string;
  interval: string;
  visibleRange: { start: number; end: number } | null;
  indicators: string[];
  activeStrategy: string | null;
  hasBacktestResult: boolean;
  tradeCount: number;
  selectedTrade: {
    entry_time: string;
    exit_time: string;
    pnl: number;
  } | null;
}

const AnalysisContext = createContext<AnalysisContextValue | null>(null);

// ============================================================================
// Provider
// ============================================================================

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(analysisReducer, initialState);

  // Get context payload for agent
  const getChartContext = useCallback((): ChartContextPayload => {
    return {
      symbol: state.chart.symbol,
      interval: state.chart.interval,
      visibleRange: state.chart.visibleRange,
      indicators: state.chart.indicators.filter(i => i.visible).map(i => i.name),
      activeStrategy: state.strategy?.name || null,
      hasBacktestResult: !!state.backtest.result,
      tradeCount: state.backtest.result?.trades.length || 0,
      selectedTrade: state.backtest.selectedTrade ? {
        entry_time: state.backtest.selectedTrade.entry_time,
        exit_time: state.backtest.selectedTrade.exit_time,
        pnl: state.backtest.selectedTrade.pnl,
      } : null,
    };
  }, [state]);

  // Emit chart event
  const emitChartEvent = useCallback((event: ChartEvent) => {
    dispatch({ type: "CHART_EVENT", event });
  }, []);

  // Add intent from agent
  const addAgentIntent = useCallback((intent: Omit<ChartIntent, "id" | "processed">) => {
    dispatch({ type: "ADD_INTENT", intent });
  }, []);

  return (
    <AnalysisContext.Provider value={{ state, dispatch, getChartContext, emitChartEvent, addAgentIntent }}>
      {children}
    </AnalysisContext.Provider>
  );
}

// ============================================================================
// Hook
// ============================================================================

export function useAnalysis() {
  const context = useContext(AnalysisContext);
  if (!context) {
    throw new Error("useAnalysis must be used within an AnalysisProvider");
  }
  return context;
}

// ============================================================================
// Utility Hooks
// ============================================================================

/**
 * Hook for chart components to process intents
 */
export function useChartIntents() {
  const { state, dispatch } = useAnalysis();

  const processIntent = useCallback((intentId: string) => {
    dispatch({ type: "PROCESS_INTENT", intentId });
  }, [dispatch]);

  return {
    intents: state.pendingIntents.filter(i => !i.processed),
    processIntent,
  };
}

/**
 * Hook for getting visible trades in current range
 */
export function useVisibleTrades() {
  const { state } = useAnalysis();

  if (!state.backtest.result?.trades || !state.chart.visibleRange) {
    return [];
  }

  const { start, end } = state.chart.visibleRange;

  return state.backtest.result.trades.filter(trade => {
    const entryTime = new Date(trade.entry_time).getTime() / 1000;
    const exitTime = new Date(trade.exit_time).getTime() / 1000;
    return entryTime >= start && exitTime <= end;
  });
}
