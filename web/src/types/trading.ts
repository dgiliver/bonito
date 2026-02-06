export interface DeployedBot {
  id: string;
  name: string;
  status: "running" | "paused" | "stopped" | "error";
  mode: "paper" | "live";
  strategy: string;
  total_trades: number;
  realized_pnl: number;
  unrealized_pnl: number;
}

export interface BotDetail extends DeployedBot {
  broker_connected: boolean;
  start_time: string;
  positions: Position[];
  pending_orders: Order[];
  performance: {
    total_trades: number;
    realized_pnl: number;
    unrealized_pnl: number;
    daily_pnl: number;
    current_equity: number;
  };
  risk: {
    score: "low" | "medium" | "high" | "extreme";
    warnings: string[];
  };
}

export interface Position {
  symbol: string;
  qty: number;
  side: "long" | "short";
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  market_value: number;
}

export interface Order {
  id: string;
  symbol: string;
  qty: number;
  side: "buy" | "sell";
  order_type: string;
  status: string;
  filled_price: number | null;
  created_at: string;
  filled_at: string | null;
}
