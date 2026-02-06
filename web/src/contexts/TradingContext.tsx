"use client";

import React, {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
} from "react";

// Types
export interface DeployedBot {
  id: string;
  name: string;
  status: "running" | "paused" | "stopped" | "error";
  mode: "paper" | "live";
  strategy: string;
  total_trades: number;
  realized_pnl: number;
  unrealized_pnl: number;
  config?: {
    name: string;
    risk_score: string;
    risk_warnings: string[];
    max_position_pct: number;
    max_daily_loss_pct: number | null;
    execution_model: string;
  };
}

export interface DeploymentConfig {
  strategy_name: string;
  strategy_config: Record<string, unknown>;
  mode: "paper" | "live";
  execution_model: "scheduled" | "continuous" | "event_driven";
  schedule?: string;
  max_position_pct: number;
  max_daily_loss_pct?: number;
  acknowledge_risks: boolean;
}

export interface AccountInfo {
  linked: boolean;
  account_id: string | null;
  account_type: "paper" | "live" | null;
  buying_power: number | null;
  api_key_preview: string | null;
}

interface TradingState {
  bots: DeployedBot[];
  selectedBot: DeployedBot | null;
  isDeploying: boolean;
  isLoading: boolean;
  error: string | null;
  account: AccountInfo;
  deploymentModalOpen: boolean;
  pendingDeployment: DeploymentConfig | null;
}

type TradingAction =
  | { type: "SET_BOTS"; bots: DeployedBot[] }
  | { type: "ADD_BOT"; bot: DeployedBot }
  | { type: "UPDATE_BOT"; bot: DeployedBot }
  | { type: "REMOVE_BOT"; botId: string }
  | { type: "SELECT_BOT"; bot: DeployedBot | null }
  | { type: "SET_DEPLOYING"; isDeploying: boolean }
  | { type: "SET_LOADING"; isLoading: boolean }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "SET_ACCOUNT"; account: AccountInfo }
  | { type: "OPEN_DEPLOYMENT_MODAL"; config?: Partial<DeploymentConfig> }
  | { type: "CLOSE_DEPLOYMENT_MODAL" }
  | { type: "SET_PENDING_DEPLOYMENT"; config: DeploymentConfig | null };

const initialState: TradingState = {
  bots: [],
  selectedBot: null,
  isDeploying: false,
  isLoading: false,
  error: null,
  account: {
    linked: false,
    account_id: null,
    account_type: null,
    buying_power: null,
    api_key_preview: null,
  },
  deploymentModalOpen: false,
  pendingDeployment: null,
};

function tradingReducer(
  state: TradingState,
  action: TradingAction,
): TradingState {
  switch (action.type) {
    case "SET_BOTS":
      return { ...state, bots: action.bots, isLoading: false };

    case "ADD_BOT":
      return { ...state, bots: [...state.bots, action.bot] };

    case "UPDATE_BOT":
      return {
        ...state,
        bots: state.bots.map((bot) =>
          bot.id === action.bot.id ? action.bot : bot,
        ),
        selectedBot:
          state.selectedBot?.id === action.bot.id
            ? action.bot
            : state.selectedBot,
      };

    case "REMOVE_BOT":
      return {
        ...state,
        bots: state.bots.filter((bot) => bot.id !== action.botId),
        selectedBot:
          state.selectedBot?.id === action.botId ? null : state.selectedBot,
      };

    case "SELECT_BOT":
      return { ...state, selectedBot: action.bot };

    case "SET_DEPLOYING":
      return { ...state, isDeploying: action.isDeploying };

    case "SET_LOADING":
      return { ...state, isLoading: action.isLoading };

    case "SET_ERROR":
      return { ...state, error: action.error };

    case "SET_ACCOUNT":
      return { ...state, account: action.account };

    case "OPEN_DEPLOYMENT_MODAL":
      return {
        ...state,
        deploymentModalOpen: true,
        pendingDeployment: action.config
          ? {
              strategy_name: "",
              strategy_config: {},
              mode: "paper",
              execution_model: "continuous",
              max_position_pct: 10,
              acknowledge_risks: false,
              ...action.config,
            }
          : null,
      };

    case "CLOSE_DEPLOYMENT_MODAL":
      return { ...state, deploymentModalOpen: false, pendingDeployment: null };

    case "SET_PENDING_DEPLOYMENT":
      return { ...state, pendingDeployment: action.config };

    default:
      return state;
  }
}

// Context
interface TradingContextValue {
  state: TradingState;
  dispatch: React.Dispatch<TradingAction>;

  // Convenience methods
  deployBot: (config: DeploymentConfig) => Promise<DeployedBot>;
  pauseBot: (botId: string) => Promise<void>;
  resumeBot: (botId: string) => Promise<void>;
  stopBot: (botId: string, closePositions?: boolean) => Promise<void>;
  refreshBots: () => Promise<void>;
  fetchAccount: () => Promise<void>;
  linkAccount: (config: {
    api_key: string;
    secret_key: string;
    account_type: "paper" | "live";
  }) => Promise<void>;
  openDeploymentModal: (config?: Partial<DeploymentConfig>) => void;
  closeDeploymentModal: () => void;
}

const TradingContext = createContext<TradingContextValue | null>(null);

// Provider
export function TradingProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(tradingReducer, initialState);

  // Fetch bots
  const refreshBots = useCallback(async () => {
    try {
      dispatch({ type: "SET_LOADING", isLoading: true });
      const response = await fetch("/api/trading/bots");
      if (!response.ok) throw new Error("Failed to fetch bots");
      const data = await response.json();
      dispatch({ type: "SET_BOTS", bots: data.bots });
    } catch (error) {
      dispatch({ type: "SET_ERROR", error: String(error) });
      dispatch({ type: "SET_LOADING", isLoading: false });
    }
  }, []);

  // Fetch account info
  const fetchAccount = useCallback(async () => {
    try {
      const response = await fetch("/api/trading/account");
      if (!response.ok) throw new Error("Failed to fetch account");
      const data = await response.json();
      dispatch({ type: "SET_ACCOUNT", account: data });
    } catch (error) {
      console.error("Failed to fetch account:", error);
    }
  }, []);

  // Deploy bot
  const deployBot = useCallback(
    async (config: DeploymentConfig): Promise<DeployedBot> => {
      dispatch({ type: "SET_DEPLOYING", isDeploying: true });
      dispatch({ type: "SET_ERROR", error: null });

      try {
        const response = await fetch("/api/trading/bots", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(config),
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to deploy bot");
        }

        const result = await response.json();

        // Create bot object from response
        const newBot: DeployedBot = {
          id: result.bot_id,
          name: result.name,
          status: result.status,
          mode: result.mode,
          strategy: config.strategy_name,
          total_trades: 0,
          realized_pnl: 0,
          unrealized_pnl: 0,
          config: {
            name: result.name,
            risk_score: result.risk_score,
            risk_warnings: result.risk_warnings || [],
            max_position_pct: config.max_position_pct,
            max_daily_loss_pct: config.max_daily_loss_pct || null,
            execution_model: config.execution_model,
          },
        };

        dispatch({ type: "ADD_BOT", bot: newBot });
        dispatch({ type: "CLOSE_DEPLOYMENT_MODAL" });

        return newBot;
      } catch (error) {
        dispatch({ type: "SET_ERROR", error: String(error) });
        throw error;
      } finally {
        dispatch({ type: "SET_DEPLOYING", isDeploying: false });
      }
    },
    [],
  );

  // Pause bot
  const pauseBot = useCallback(
    async (botId: string) => {
      try {
        const response = await fetch(`/api/trading/bots/${botId}/pause`, {
          method: "POST",
        });
        if (!response.ok) throw new Error("Failed to pause bot");

        // Update local state
        const bot = state.bots.find((b) => b.id === botId);
        if (bot) {
          dispatch({ type: "UPDATE_BOT", bot: { ...bot, status: "paused" } });
        }
      } catch (error) {
        dispatch({ type: "SET_ERROR", error: String(error) });
        throw error;
      }
    },
    [state.bots],
  );

  // Resume bot
  const resumeBot = useCallback(
    async (botId: string) => {
      try {
        const response = await fetch(`/api/trading/bots/${botId}/resume`, {
          method: "POST",
        });
        if (!response.ok) throw new Error("Failed to resume bot");

        // Update local state
        const bot = state.bots.find((b) => b.id === botId);
        if (bot) {
          dispatch({ type: "UPDATE_BOT", bot: { ...bot, status: "running" } });
        }
      } catch (error) {
        dispatch({ type: "SET_ERROR", error: String(error) });
        throw error;
      }
    },
    [state.bots],
  );

  // Stop bot
  const stopBot = useCallback(
    async (botId: string, closePositions = false) => {
      try {
        const response = await fetch(
          `/api/trading/bots/${botId}/stop?close_positions=${closePositions}`,
          { method: "POST" },
        );
        if (!response.ok) throw new Error("Failed to stop bot");

        // Update local state
        const bot = state.bots.find((b) => b.id === botId);
        if (bot) {
          dispatch({ type: "UPDATE_BOT", bot: { ...bot, status: "stopped" } });
        }
      } catch (error) {
        dispatch({ type: "SET_ERROR", error: String(error) });
        throw error;
      }
    },
    [state.bots],
  );

  // Link account
  const linkAccount = useCallback(
    async (config: {
      api_key: string;
      secret_key: string;
      account_type: "paper" | "live";
    }) => {
      try {
        const response = await fetch("/api/trading/account/link", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(config),
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || "Failed to link account");
        }

        const data = await response.json();
        dispatch({ type: "SET_ACCOUNT", account: data });

        // Refresh bots after linking
        await refreshBots();
      } catch (error) {
        throw error;
      }
    },
    [refreshBots],
  );

  // Modal helpers
  const openDeploymentModal = useCallback(
    (config?: Partial<DeploymentConfig>) => {
      dispatch({ type: "OPEN_DEPLOYMENT_MODAL", config });
    },
    [],
  );

  const closeDeploymentModal = useCallback(() => {
    dispatch({ type: "CLOSE_DEPLOYMENT_MODAL" });
  }, []);

  // Initial fetch
  useEffect(() => {
    refreshBots();
    fetchAccount();

    // Poll every 10 seconds
    const interval = setInterval(refreshBots, 10000);
    return () => clearInterval(interval);
  }, [refreshBots, fetchAccount]);

  const value: TradingContextValue = {
    state,
    dispatch,
    deployBot,
    pauseBot,
    resumeBot,
    stopBot,
    refreshBots,
    fetchAccount,
    linkAccount,
    openDeploymentModal,
    closeDeploymentModal,
  };

  return (
    <TradingContext.Provider value={value}>{children}</TradingContext.Provider>
  );
}

// Hook
export function useTrading() {
  const context = useContext(TradingContext);
  if (!context) {
    throw new Error("useTrading must be used within a TradingProvider");
  }
  return context;
}

// Export types for use elsewhere
export type { TradingState, TradingAction, TradingContextValue };
