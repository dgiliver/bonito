# Feature Backlog

Prioritized list of features beyond the core MVP.

---

## 🔥 High Priority (Post-MVP Phase 1)

### F001: Custom Formula Indicators
**Status**: Planned
**Effort**: 1-2 days
**Value**: High - Users can create indicators without code

Allow mathematical expressions in strategy DSL:
```json
{
  "type": "custom",
  "name": "momentum_10",
  "formula": "(close - close[10]) / close[10] * 100"
}
```

**Requirements**:
- Safe expression parser (no eval)
- Support: `+`, `-`, `*`, `/`, `abs`, `max`, `min`
- Lookback syntax: `close[N]` for N bars ago
- Cross-indicator references: `sma_20 - sma_50`

---

### F002: Strategy Plugin Interface
**Status**: Planned
**Effort**: 3-4 days
**Value**: High - Power users can implement any logic

```python
class MyStrategy(StrategyBase):
    name = "custom_momentum"
    parameters = {"lookback": 10}

    def compute_signals(self, data: BarData) -> np.ndarray:
        # Full Python freedom
        ...
```

**Requirements**:
- `StrategyBase` abstract class
- Auto-discovery from `strategies/` folder
- Parameter schema for agent tuning
- Unit test template for user strategies

---

### F003: Strategy Comparison Tool
**Status**: Planned
**Effort**: 1 day
**Value**: Medium - Compare multiple strategies side-by-side

```bash
quant compare strategy1.json strategy2.json --symbol SPY
```

Output: Side-by-side metrics, equity curve overlay, correlation analysis.

---

## 🟡 Medium Priority (Post-MVP Phase 2)

### F004: Sandboxed Python Execution
**Status**: Backlog
**Effort**: 1-2 weeks
**Value**: Medium - Untrusted code execution

Run user-uploaded Python in isolated Docker/subprocess:
- Restricted imports (whitelist only)
- Memory/CPU limits
- No network access
- Timeout enforcement

---

### F005: Walk-Forward Optimization
**Status**: Backlog
**Effort**: 3-4 days
**Value**: High - Reduce overfitting

Split data into train/test windows, optimize on train, validate on test.
Agent can use this to avoid curve-fitting.

---

### F006: Multi-Symbol Portfolio Backtesting
**Status**: Backlog
**Effort**: 3-5 days
**Value**: High - Real portfolio strategies

Run same strategy across multiple tickers with shared account capital.

**Example:**
```
Account: $100,000
Strategy: EMA Crossover
Symbols: [AAPL, MSFT, TSLA, GOOGL]
Max per position: 25%
Max concurrent: 4
```

**Backend Requirements:**
- Scan all symbols each bar for signals
- Shared capital pool allocation
- Track positions across symbols
- Portfolio-level equity curve
- Portfolio metrics (Sharpe, correlation, etc.)

**Position Sizing Options:**
- Equal weight (simple)
- Risk parity
- Correlation-aware allocation
- Sector exposure limits

**Frontend:**
- Per-symbol trade breakdown
- Portfolio composition chart over time
- Combined vs per-symbol performance

---

### F007: Alpaca Integration & Paper Trading
**Status**: Backlog
**Effort**: 2 weeks
**Value**: High - Real-time validation & execution

Full Alpaca integration for data + trading.

**Phase 1: OAuth & Data**
- Alpaca OAuth flow (user connects their account)
- Historical data (unlimited bars)
- Real-time WebSocket streaming
- Account balance display

**Phase 2: Paper Trading**
- Execute orders in Alpaca paper account
- Position tracking
- P&L in real-time
- Strategy performance vs backtest comparison

**Phase 3: Live Trading** (careful!)
- Same API, live account
- Risk controls required
- Position size limits
- Kill switch

**API Integration:**
```python
class AlpacaClient:
    async def connect(oauth_token: str)
    async def get_account() -> Account
    async def get_bars(symbol, timeframe, start, end) -> BarData
    async def stream_bars(symbols) -> AsyncIterator[Bar]
    async def submit_order(symbol, qty, side, type) -> Order
    async def get_positions() -> list[Position]
```

---

## 🟡 Medium Priority (Post-MVP Phase 2)

### F010: Optimized Data Collection
**Status**: Backlog
**Effort**: 2-3 days
**Value**: High - Better intraday data coverage

Current Yahoo Finance limitations:
- 1m: 7 days max
- 5m: 60 days max
- 1h: 730 days max

**Improvements**:
1. **Alpaca Integration** (free, real-time)
   - Unlimited historical bars
   - Real-time streaming
   - Paper trading ready
2. **Polygon.io** (paid, comprehensive)
   - Full market data
   - Options, forex, crypto
3. **Data Caching Layer**
   - Smart date range requests
   - Avoid redundant downloads
   - Background refresh

---

## 🟡 Medium Priority (Post-MVP Phase 2)

### F014: Symbol Search & Discovery
**Status**: Backlog
**Effort**: 1 day
**Value**: High - Better UX for data ingestion

Search for symbols by company name instead of requiring exact tickers.

**Features:**
- Autocomplete search ("Apple" → AAPL)
- Company info display (name, sector, market cap)
- Filter by asset class (stocks, ETFs, crypto)
- Recently used symbols
- Popular/trending symbols

**Implementation:**
- Yahoo Finance search API (free)
- Alpha Vantage symbol search (backup)
- Local cache for common symbols

---

### F015: Multi-Tenant Architecture
**Status**: Backlog
**Effort**: 1-2 weeks
**Value**: Critical for SaaS/team deployment

Support multiple users with isolated data and resources.

**Authentication:**
- OAuth (Google, GitHub) via Clerk/Auth0/Supabase
- Session management
- API key per user

**Data Isolation:**
- Separate strategies per user
- Separate market data (or shared with access control)
- Private conversations
- Row-level security in PostgreSQL

**Resource Management:**
- Usage tracking (API calls, backtests)
- Rate limits per tier
- Storage quotas

**Billing (optional):**
- Free tier: X backtests/month
- Pro tier: Unlimited + priority
- Team tier: Collaboration features

---

### F016: Additional Data Sources
**Status**: Backlog
**Effort**: 2-3 days per source
**Value**: High - Better data coverage

Move beyond Yahoo Finance limitations.

**Priority sources:**
1. **Alpaca** (free, real-time, paper trading ready)
2. **Polygon.io** (paid, comprehensive)
3. **Tiingo** (free tier, reliable EOD)
4. **Binance** (crypto real-time)

**Unified interface:**
```python
class DataProvider(ABC):
    async def get_bars(symbol, start, end, timeframe) -> BarData
    async def search_symbols(query) -> list[Symbol]
    async def stream_bars(symbol) -> AsyncIterator[Bar]
```

**Fallback chain:** Try Alpaca → Yahoo → Tiingo

---

## 🟢 Nice to Have (Future)

### F013: Conversation Persistence
**Status**: Backlog
**Effort**: 1 day
**Value**: Medium - Resume previous agent sessions

Save chat conversations to disk and allow users to:
- Resume previous sessions
- Browse conversation history
- Search past interactions
- Export conversations

**Implementation**:
- Store in `data/conversations/{session_id}.json`
- Include timestamps, messages, tool calls
- Add "History" panel in sidebar
- Session selector dropdown

---

### F017: Crypto Trading Support
**Status**: Backlog
**Effort**: 3-5 days
**Value**: High - Large market, free data

Extend platform to support cryptocurrency trading.

**Data Sources (free):**
- Binance API (most liquid)
- Coinbase Pro (US-friendly)
- Kraken, KuCoin, etc.

**Unique Considerations:**
- 24/7 markets (no hours/holidays)
- Multiple exchanges with price differences
- Higher volatility profiles
- Perpetual futures & funding rates

**Implementation:**
- Crypto data provider class
- 24/7 timeframe handling
- Symbol format: BTC-USD, ETH-USDT
- Exchange selection in UI

**Crypto-specific indicators:**
- Funding rate
- Exchange inflows/outflows
- Whale wallet tracking (advanced)

---

### F018: Options Trading Support
**Status**: Backlog
**Effort**: 3-4 weeks
**Value**: Very High - Untapped market, complex moat

Full options backtesting and strategy support.

**Data Requirements:**
- Historical options chains (strikes × expirations)
- Implied Volatility time series
- Greeks (Delta, Gamma, Theta, Vega)
- Bid/ask spreads

**Data Sources (paid):**
- Polygon.io ($29+/mo)
- CBOE (expensive)
- Tastytrade (limited free)

**Strategy Types to Support:**
- Single leg (calls, puts)
- Vertical spreads (bull call, bear put)
- Iron condors, butterflies
- Straddles, strangles
- Calendar spreads

**DSL Extension:**
```json
{
  "legs": [
    {"underlying": "SPY", "strike": 450, "expiry": "2024-03-15",
     "type": "call", "action": "buy", "quantity": 1},
    {"underlying": "SPY", "strike": 460, "expiry": "2024-03-15",
     "type": "call", "action": "sell", "quantity": 1}
  ]
}
```

**Backtesting Complexity:**
- Non-linear P&L calculation
- Time decay simulation
- IV change impact
- Assignment/exercise handling
- Expiration rolling

**Greeks Calculation:**
- Black-Scholes model
- Or fetch from data provider
- Display in UI

---

### F008: Strategy Marketplace
Share and discover community strategies.

### F009: Natural Language Backtests
"How would a 50/200 SMA cross have performed on AAPL last year?"

### F010: Automated Strategy Reports
Generate PDF reports with charts, metrics, and agent commentary.

### F011: Real-Time Alerts
Notify when strategy signals trigger on live data.

### F012: Multi-Timeframe Strategies
Combine signals from daily + hourly data.

---

## Completed Features

| ID | Feature | Completed | Notes |
|----|---------|-----------|-------|
| - | Market Data Ingestion | Week 1 | Yahoo Finance + DuckDB |
| - | Vectorized Backtest Engine | Week 2 | 7 indicators, DSL strategies |
| - | CLI Interface | Week 2 | ingest, data, backtest commands |
| - | AI Agent (Claude) | Week 3 | ReAct loop, tool calling |
| - | Strategy Save/Load | Week 3 | JSON persistence |
| - | Multi-timeframe Support | Week 3 | 1m, 5m, 15m, 1h, 4h, 1d |
| - | FastAPI Server | Week 4 | REST API + SSE streaming |
| - | Docker Setup | Week 4 | Dockerfile + docker-compose |
| - | Next.js Web UI | Week 4 | Chat, Strategies, Data views |
| - | Markdown Rendering | Week 4 | react-markdown for agent responses |
| - | Quick Action Buttons | Week 4 | Save, Backtest, New Chat |

---

*Last updated: Week 4 - Web UI*
