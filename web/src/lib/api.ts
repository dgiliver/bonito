/**
 * API client for the Bonito FastAPI backend.
 *
 * Base URL pattern matches the existing convention used in
 * `components/analysis/IntelligentChartV2.tsx`.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ============================================================================
// Shared helpers
// ============================================================================

/** Extract a useful error message from a non-2xx FastAPI response. */
async function extractErrorMessage(res: Response, fallback: string): Promise<string> {
  const data = await res.json().catch(() => null);
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(await extractErrorMessage(res, `Request to ${path} failed (${res.status})`));
  }
  return res.json() as Promise<T>;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(await extractErrorMessage(res, `Request to ${path} failed (${res.status})`));
  }
  return res.json() as Promise<T>;
}

// ============================================================================
// Chat — POST /api/chat (SSE)
// ============================================================================

/** Discriminated union of all SSE events streamed from POST /api/chat. */
export type ChatEvent =
  | { type: "session"; session_id: string }
  | { type: "tool_call"; tool: string; args: Record<string, unknown> }
  | { type: "tool_result"; tool: string; success: boolean; data: unknown }
  | { type: "response"; content: string }
  | { type: "error"; error: string }
  | { type: "done" };

/**
 * Stream a chat message to the agent and surface each SSE event via `onEvent`.
 *
 * Resolves with the session id (captured from the initial `session` event)
 * once the stream completes, or `null` if the session id was never received
 * (e.g. the request failed before the backend could respond).
 */
export async function streamChat(
  message: string,
  sessionId: string | null,
  onEvent: (event: ChatEvent) => void,
  onError: (error: string) => void,
): Promise<string | null> {
  let resolvedSessionId: string | null = null;

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });

    if (!res.ok) {
      onError(await extractErrorMessage(res, `Chat request failed (${res.status})`));
      return null;
    }

    if (!res.body) {
      onError("Chat response had no body");
      return null;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const messages = buffer.split("\n\n");
      // Keep the last (possibly incomplete) chunk in the buffer.
      buffer = messages.pop() ?? "";

      for (const chunk of messages) {
        const line = chunk.trim();
        if (!line.startsWith("data: ")) continue;

        const payload = line.slice("data: ".length);
        let event: ChatEvent;
        try {
          event = JSON.parse(payload) as ChatEvent;
        } catch {
          continue;
        }

        if (event.type === "session") {
          resolvedSessionId = event.session_id;
        } else if (event.type === "error") {
          onError(event.error);
        }

        onEvent(event);
      }
    }

    return resolvedSessionId;
  } catch (err) {
    onError(err instanceof Error ? err.message : "Failed to stream chat response");
    return resolvedSessionId;
  }
}

// ============================================================================
// Strategies — GET /api/strategies
// ============================================================================

/** Strategy summary as returned by GET /api/strategies. */
export interface StrategySummary {
  id: string;
  name: string;
  description: string;
  version: string;
  tags: string[];
  updated_at: string;
  last_backtest?: {
    symbol: string;
    total_return: number;
    sharpe_ratio: number;
    max_drawdown: number;
  };
}

export interface FetchStrategiesResponse {
  strategies: StrategySummary[];
  count: number;
}

export async function fetchStrategies(): Promise<FetchStrategiesResponse> {
  return getJson<FetchStrategiesResponse>("/api/strategies");
}

// ============================================================================
// Backtest — POST /api/backtest/run
// ============================================================================

export interface RunBacktestRequest {
  symbol: string;
  start_date?: string;
  end_date?: string;
  initial_capital?: number;
  commission?: number;
  strategy_config?: Record<string, unknown>;
  strategy_name?: string;
}

export interface BacktestTradeLogEntry {
  entry_time: string;
  exit_time: string;
  side: string;
  position_side: "long" | "short";
  quantity: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  return_pct: string;
  exit_reason: string;
}

export interface BacktestEquityPoint {
  date: string;
  equity: number;
  drawdown: number;
  benchmark: number;
}

export interface RunBacktestResponse {
  symbol: string;
  strategy: string;
  period: { start: string; end: string; bars: number };
  performance: {
    total_return: number;
    total_return_pct: string;
    sharpe_ratio: number;
    max_drawdown: number;
    max_drawdown_pct: string;
    win_rate: number;
    win_rate_pct: string;
    profit_factor: number;
  };
  trades: { total: number; winning: number; losing: number };
  capital: { initial: number; final: number; profit: number };
  trade_log: BacktestTradeLogEntry[];
  equity_curve: BacktestEquityPoint[];
}

export async function runBacktest(request: RunBacktestRequest): Promise<RunBacktestResponse> {
  return postJson<RunBacktestResponse>("/api/backtest/run", request);
}

// ============================================================================
// Data — GET /api/data/symbols, POST /api/data/ingest
// ============================================================================

export interface SymbolInfo {
  symbol: string;
  start: string;
  end: string;
  bars: number;
}

export interface FetchSymbolsResponse {
  symbols: SymbolInfo[];
  count: number;
}

export async function fetchSymbols(): Promise<FetchSymbolsResponse> {
  return getJson<FetchSymbolsResponse>("/api/data/symbols");
}

export interface IngestDataRequest {
  symbols: string[];
  start: string;
  end?: string;
  timeframe?: string;
}

export interface IngestDataResult {
  symbol: string;
  bars: number;
  status: "success" | "error";
  error?: string;
}

export interface IngestDataResponse {
  results: IngestDataResult[];
  total_bars: number;
  timeframe: string;
}

export async function ingestData(request: IngestDataRequest): Promise<IngestDataResponse> {
  return postJson<IngestDataResponse>("/api/data/ingest", request);
}
