# Feature Backlog

Prioritized list of features beyond the core MVP.

---

## ⚠️ Strategy Architecture Limitations

**Analysis from a senior quant trader perspective:** The current DSL can express basic retail strategies (MA crossovers, RSI mean reversion) but hits walls quickly with anything institutional-grade. Here's what a hedge fund PM would ask for that we can't do:

### Critical Gaps

#### 1. **Long-Only Constraint**
The engine only supports BUY orders. Can't short, can't hedge, can't do market-neutral strategies. A PM would immediately ask: "Can I short TSLA when it goes overbought?" — **No.**

*Impact:* Eliminates ~50% of strategy universe. No pair trading, no stat arb, no long/short equity.

#### 2. **Single Symbol Execution**
Even though `symbols` accepts a list, the engine only trades `symbols[0]`. Can't express:
- "Buy AAPL when MSFT breaks out" (cross-asset signals)
- "Long XLK, short XLF when tech/financials ratio crosses threshold" (sector rotation)
- "Buy gold when VIX spikes" (flight-to-safety)

*Impact:* No relative value, no cross-asset, no macro strategies.

#### 3. **No Position Memory / State**
Strategies are stateless. Can't track:
- "Bars since entry" (for time-based exits)
- "Number of adds to this position" (for pyramiding)
- "Previous trade outcome" (for anti-martingale)
- "Consecutive losing trades" (for risk adjustment)

*Impact:* Can't implement sophisticated position management or adaptive sizing.

#### 4. **Static Position Sizing**
Position size is determined once at entry. Can't do:
- Volatility targeting ("maintain 15% annualized vol")
- Kelly criterion ("size based on edge")
- ATR-based sizing ("risk $X per ATR")
- Conviction-based ("RSI at 10 = full size, RSI at 25 = half size")

*Impact:* Suboptimal capital allocation, can't implement proper risk management.

#### 5. **All-or-Nothing Execution**
No scaling in/out. Real traders:
- Scale into positions (buy 25% at first signal, add on confirmation)
- Scale out (take 50% profit at 2R, let rest run)
- Average down in mean reversion strategies

*Impact:* Binary entry/exit doesn't match how professionals trade.

### Moderate Gaps

#### 6. **No Lookback Window Conditions**
Current: "IF RSI < 30" (point-in-time check)
Need: "IF RSI was below 30 at any point in last 5 bars" (window check)
Need: "IF close is at 20-day high" (rolling extrema)
Need: "IF volume > 2x 20-day average" (relative comparisons)

#### 7. **Single Timeframe Only**
Can't combine:
- Daily trend direction + hourly entry timing
- Weekly regime + daily signals
- 1h structure + 5m precision entries

This is how most professionals trade. MTF analysis is table stakes.

#### 8. **Flat Rule Logic**
Only AND/OR within a rule. Can't express:
- "At least 2 of 3 conditions must be true"
- "Score: RSI<30 = +1, MACD cross = +1, above SMA = +1, enter if score >= 2"
- Weighted condition importance

#### 9. **No Time-Based Filters**
Can't restrict:
- Trading hours (only trade 9:30-10:30 AM)
- Day of week (no Mondays)
- Events (avoid FOMC days, earnings weeks)
- Seasonality (sell in May)

#### 10. **No Trailing Stops**
Only fixed stops. Can't do:
- "Trail stop at 2 ATR below highest close since entry"
- "Move stop to breakeven after 1R profit"
- Chandelier exits

#### 11. **No Re-Entry Logic**
Can't specify:
- "Don't re-enter within 5 bars of exit"
- "Max 3 trades per day"
- "No new positions if already stopped out today"

#### 12. **No Regime Awareness**
Can't adapt to market conditions:
- "Only mean revert when VIX > 25"
- "Use tighter stops in low-vol environments"
- "Switch to trend-following when ADX > 25"

### What This Means for Custom Strategies (F002)

The plugin interface becomes **critical** — it's not just "nice to have" for power users. It's the escape hatch for anyone who wants to implement real strategies. The DSL should handle 80% of retail use cases, but the plugin system handles the 20% that makes strategies actually tradeable.

**Priority should be:**
1. F002 (Plugin Interface) — immediate, opens up everything
2. Short selling support — doubles strategy universe
3. Multi-symbol execution — enables relative value
4. State/memory — enables position management
5. MTF analysis — professional standard

---

## ⚠️ Indicator Gap Analysis

**Current indicators (7):** SMA, EMA, RSI, MACD, ATR, Bollinger Bands, Stochastic

**What a senior trader would immediately ask for:**

### Missing: Volume-Based Indicators (we have ZERO)
Volume analysis is fundamental to institutional trading. Without it, you can't distinguish real moves from fakeouts.

| Indicator | Use Case | Priority |
|-----------|----------|----------|
| **VWAP** | Institutional benchmark, mean reversion anchor | 🔥 Critical |
| **OBV** (On-Balance Volume) | Accumulation/distribution, divergence | High |
| **CMF** (Chaikin Money Flow) | Money flow strength | Medium |
| **MFI** (Money Flow Index) | RSI but volume-weighted | Medium |
| **A/D Line** | Accumulation/Distribution | Medium |
| **Volume SMA** | Relative volume spikes | High |

*"Is this breakout real or fake?"* — Can't answer without volume.

### Missing: Trend Strength
We have trend direction (MA crossovers) but not trend *strength*.

| Indicator | Use Case | Priority |
|-----------|----------|----------|
| **ADX** | "Is this trending or ranging?" — changes strategy entirely | 🔥 Critical |
| **Parabolic SAR** | Trailing stop placement, trend reversals | Medium |
| **SuperTrend** | Cleaner trend signals than MA crosses | Medium |
| **Ichimoku Cloud** | Full system: trend, momentum, S/R | Nice-to-have |

*"Should I use mean reversion or trend following right now?"* — Need ADX.

### Missing: Channels & Breakout Tools

| Indicator | Use Case | Priority |
|-----------|----------|----------|
| **Donchian Channels** | Breakout trading (Turtle strategy) | High |
| **Keltner Channels** | Volatility-adjusted channels | Medium |
| **Pivot Points** | Daily S/R levels | Medium |
| **ATR Bands** | Volatility envelopes | Medium |

### Missing: Momentum Variants

| Indicator | Use Case | Priority |
|-----------|----------|----------|
| **CCI** | Mean reversion, different math than RSI | Medium |
| **Williams %R** | Fast overbought/oversold | Low |
| **ROC** (Rate of Change) | Pure momentum | Medium |
| **TSI** (True Strength Index) | Smoothed momentum | Low |

### Missing: Computed/Derived Values
Not indicators per se, but essential calculations:

| Calculation | Use Case | Priority |
|-------------|----------|----------|
| **Rolling High/Low** | "20-day high", breakout detection | 🔥 Critical |
| **Z-Score** | Mean reversion setups | High |
| **Percentile Rank** | "RSI is in bottom 5% of last 100 readings" | High |
| **Normalized ATR** | ATR as % of price for cross-asset comparison | Medium |
| **Ratio/Spread** | Pairs trading, relative value | High |

### Recommendation: Integrate pandas-ta

Rather than implementing 50+ indicators by hand, integrate **pandas-ta** (130+ indicators) or **TA-Lib** (150+ indicators).

**pandas-ta advantages:**
- Pure Python/NumPy/Pandas (no C dependencies like TA-Lib)
- 130+ indicators across all categories
- Active maintenance
- Easy integration with our existing NumPy arrays

**Implementation approach:**
```python
# In indicators.py
import pandas_ta as ta

def compute_indicators(data: BarData, indicators: list[IndicatorConfig]) -> dict:
    df = pd.DataFrame({
        'open': data.open, 'high': data.high,
        'low': data.low, 'close': data.close, 'volume': data.volume
    })

    for config in indicators:
        if config.type == "vwap":
            df.ta.vwap(append=True)
        elif config.type == "adx":
            df.ta.adx(length=config.params.get("period", 14), append=True)
        # ... etc
```

**Effort estimate:** 1-2 days to integrate pandas-ta, then all 130+ indicators available.

---

## 🔥 High Priority (Post-MVP Phase 1)

### ~~F019: pandas-ta Integration~~ ✅ COMPLETED
**Status**: ✅ Completed (v0.5.0)
**Effort**: 1.5 days (as estimated)
**Value**: Very High - 130+ indicators now available

Integrated pandas-ta library with:
- Volume indicators (VWAP, OBV, MFI, CMF)
- Trend strength (ADX with DI+/DI-, SuperTrend, Aroon)
- Channels (Donchian, Keltner)
- 130+ more indicators via string type in IndicatorConfig

**Implementation:**
- Added pandas-ta to dependencies
- Created BarData → DataFrame adapter
- Flexible type system: accepts enum or string indicator names
- Multi-column output handling (ADX, Donchian, etc.)
- Full backward compatibility maintained
- 28 new tests for pandas-ta indicators

**Example usage in strategy:**
```json
{
  "indicators": [
    {"type": "vwap", "name": "vwap"},
    {"type": "adx", "name": "trend", "params": {"length": 14}},
    {"type": "donchian", "name": "dc", "params": {"lower_length": 20, "upper_length": 20}}
  ]
}
```

---

### F020: Short Selling Support
**Status**: Planned
**Effort**: 2-3 days
**Value**: Critical - Doubles strategy universe

Add ability to short. Requires:
- New `side` field in entry rules: `"side": "short"` or `"side": "long"`
- Short P&L calculation (entry - exit, not exit - entry)
- Short position tracking in engine
- Margin/buying power considerations (optional for backtest)

**Example:**
```json
{
  "entry_rules": [
    {
      "side": "short",
      "conditions": [{"left": "rsi", "comparison": "gt", "right": 80}]
    }
  ]
}
```

---

### F022: Rolling Lookback Conditions
**Status**: Planned
**Effort**: 2-3 days
**Value**: High - Enables real breakout/window-based strategies

Add ability to reference rolling windows in conditions:

**New condition syntax:**
```json
{
  "left": "close",
  "comparison": "gte",
  "right": "rolling_max(close, 20)"  // 20-day high breakout
}
// or
{
  "left": "rsi",
  "comparison": "was_below",
  "right": 30,
  "lookback": 5  // RSI was below 30 at some point in last 5 bars
}
// or
{
  "left": "volume",
  "comparison": "gt",
  "right": "sma(volume, 20) * 2"  // Volume > 2x average
}
```

**New computed values:**
- `rolling_max(series, period)` - N-period high
- `rolling_min(series, period)` - N-period low
- `rolling_mean(series, period)` - Same as SMA but inline
- `zscore(series, period)` - Z-score for mean reversion
- `percentile(series, period)` - Percentile rank

**Engine changes:**
- Pre-compute rolling stats as "virtual indicators"
- Parse expressions in condition right-hand side
- Add `was_above` / `was_below` comparisons with lookback

---

### F021: Trailing Stops ✅ COMPLETE
**Status**: Complete (v0.6.0)
**Effort**: 1 day
**Value**: High - Essential for trend-following

Add trailing stop capability:
- Trail by fixed percent from high-water mark
- Trail by ATR multiple
- Move to breakeven after X% profit

**New stop_loss types:**
```json
{
  "stop_loss": {
    "type": "trailing_percent",
    "value": 0.05
  }
}
// or
{
  "stop_loss": {
    "type": "trailing_atr",
    "value": 2.0,
    "atr_period": 14
  }
}
```

**Engine changes:**
- Track highest price since entry per position
- Update stop level each bar
- Check against trailing stop, not just entry-based stop

---

### F024: UI Virtualization & Large Data Handling ✅ COMPLETE
**Status**: Complete (v0.7.0)
**Effort**: 1-2 days
**Value**: High - UX bug fix + scalability

Multiple UI components don't handle large data well. This is a unified fix using virtualization (best practice).

**Issues:**
1. **Chat Window:**
   - Long agent responses overflow container
   - Code blocks may not wrap properly
   - Auto-scroll to bottom inconsistent
   - Performance degrades with long conversations

2. **Trade Log:**
   - Currently hard-limited to 50 trades (`backtest.py[:50]`)
   - Users can't see full trade history
   - Need to support 1000+ trades smoothly

3. **Equity Curve:**
   - Downsampled to 200 points - acceptable for now

**Solution: Virtualized Lists**

Use `@tanstack/react-virtual` or `react-window` for:
- Chat messages
- Trade log table
- Any list that could grow large

**Implementation:**

```typescript
// Trade log with virtualization
import { useVirtualizer } from '@tanstack/react-virtual';

function TradeLog({ trades }: { trades: Trade[] }) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: trades.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48, // Row height
  });

  return (
    <div ref={parentRef} className="h-[400px] overflow-auto">
      <div style={{ height: `${virtualizer.getTotalSize()}px` }}>
        {virtualizer.getVirtualItems().map((virtualRow) => (
          <TradeRow key={virtualRow.key} trade={trades[virtualRow.index]} />
        ))}
      </div>
    </div>
  );
}
```

**Backend Changes:**
- Remove `[:50]` limit in `backtest.py`
- Return all trades (frontend handles rendering)

**Requirements:**
- [ ] Install `@tanstack/react-virtual`
- [ ] Virtualize trade log table
- [ ] Virtualize chat message list
- [ ] Proper overflow handling with scroll
- [ ] Code blocks: horizontal scroll, not break layout
- [ ] Auto-scroll to latest message
- [ ] Test with 500+ trades, 100+ messages

---

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

### F023: Delete Market Data
**Status**: Planned
**Effort**: 0.5 day
**Value**: High - Essential data management

Allow users to delete ingested market data (symbols/date ranges).

**Requirements**:
- API endpoint: `DELETE /api/data/{symbol}` or `DELETE /api/data/{symbol}?start=&end=`
- CLI command: `bonito data delete AAPL` or `bonito data delete AAPL --start 2024-01-01`
- UI: Delete button in Data view per symbol
- Confirmation dialog (prevent accidental deletion)
- Cascade: Handle strategies that reference deleted data gracefully

**Example API:**
```
DELETE /api/data/AAPL              # Delete all AAPL data
DELETE /api/data/AAPL?timeframe=1h # Delete only 1h AAPL data
```

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

### F025: Advanced Financial Charts & Visualization
**Status**: In Progress (Phase 1-2 Complete)
**Effort**: 5 weeks total (Phase 1-2 done, Phase 3-5 remaining)
**Value**: Very High - Professional-grade charting is table stakes

Comprehensive financial timeseries visualization using Lightweight Charts (TradingView's open-source library).

#### ✅ Phase 1-2 Complete: Visual Language Synthesis

**Novel Feature:** Agent-Chart integration that enables conversational visual analysis.

The chart and AI agent now share context:
- Agent knows what symbol/timeframe user is viewing
- Trade markers appear automatically from backtest results
- Click trade markers to select and see details
- Unified AnalysisView combines chart + chat in one view

```
┌────────────────────────────────────────────────────────────────┐
│                   UNIFIED ANALYSIS VIEW                        │
├───────────────────────────────────┬────────────────────────────┤
│                                   │                            │
│     INTELLIGENT CHART             │    CONTEXT-AWARE CHAT      │
│  • Candlesticks + Volume          │  • Agent sees chart state  │
│  • Trade markers (▲ entry ▼ exit) │  • Backtest results update │
│  • Click trade → see details      │  • Strategy-aware responses│
│                                   │                            │
└───────────────────────────────────┴────────────────────────────┘
```

**Components Built:**
- `AnalysisContext.tsx` - Shared state for chart-agent communication
- `AnalysisView.tsx` - Unified view with chart + chat panel
- `IntelligentChart.tsx` - Chart with trade markers and click handling
- `ChartIntent` system for agent → chart control (foundation)

**📖 Integration Rules:** See `.cursor/rules/bonito-standards.mdc` (Agent-Chart Synthesis section) for mandatory integration checklist. Extended examples in [`docs/AGENT_CHART_SYNTHESIS.md`](./AGENT_CHART_SYNTHESIS.md).

#### Remaining Phases

#### Chart Types
- **Candlestick charts** - Standard OHLC candles
- **OHLC bar charts** - Traditional bar format
- **Line charts** - For indicators and overlays
- **Area charts** - For equity curves, volume
- **Heikin-Ashi candles** - Smoothed trend visualization
- **Baseline charts** - Show deviation from baseline (e.g., VWAP)

#### Price Overlays
- Moving averages (SMA, EMA, etc.) with customizable colors
- Bollinger Bands with fill
- Keltner Channels
- Donchian Channels
- VWAP with standard deviation bands
- SuperTrend
- Ichimoku Cloud (future)
- Support/Resistance levels
- Trend lines (manual or auto-detected)
- Fibonacci retracements

#### Oscillator Panels (Below Chart)
- RSI with overbought/oversold zones
- MACD with histogram
- Stochastic %K/%D
- Volume bars (colored by direction)
- OBV
- ATR
- ADX with DI+/DI-
- CCI, MFI, ROC, etc.

#### Trade Visualization
- Entry/exit markers on chart
- Trade annotations with P&L
- Drawdown shading (red fill during drawdown periods)
- Position size visualization
- Stop loss / take profit lines

#### Backtest Results View
- Equity curve chart
- Drawdown chart
- Trade distribution histogram
- Monthly returns heatmap
- Rolling Sharpe ratio
- Win/loss streak visualization

#### Interactivity
- Zoom and pan (mouse wheel, drag)
- Crosshair with OHLCV tooltip
- Time range selector (1D, 1W, 1M, 3M, 1Y, ALL)
- Toggle indicators on/off
- Click on trade marker to see details
- Sync multiple charts (same symbol, different timeframes)

#### Technical Implementation
```
Frontend (Next.js):
├── lightweight-charts (TradingView)
├── Custom indicator renderers
├── Chart state management
└── WebSocket for real-time updates (future)

Backend (FastAPI):
├── /api/charts/ohlcv/{symbol} - OHLCV data for charting
├── /api/charts/indicators - Computed indicator data
├── /api/charts/trades/{strategy} - Trade markers
└── /api/charts/equity/{backtest_id} - Equity curve data
```

#### Example Chart Configuration
```typescript
{
  symbol: "SPY",
  timeframe: "1d",
  dateRange: { start: "2024-01-01", end: "2024-12-01" },
  overlays: [
    { type: "sma", period: 20, color: "#2196F3" },
    { type: "sma", period: 50, color: "#FF9800" },
    { type: "bbands", period: 20, stdDev: 2, fillColor: "rgba(33, 150, 243, 0.1)" }
  ],
  panels: [
    { type: "volume", height: 100 },
    { type: "rsi", period: 14, height: 150, overbought: 70, oversold: 30 },
    { type: "macd", height: 150 }
  ],
  trades: "backtest_123"  // Show trades from this backtest
}
```

#### Milestones
1. **Phase 1** (2 days): Basic candlestick chart with price overlays
2. **Phase 2** (1 day): Oscillator panels (RSI, MACD, Volume)
3. **Phase 3** (1 day): Trade markers and equity curve
4. **Phase 4** (1 day): Interactivity, time range selector, polish

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
| F019 | pandas-ta Integration | Week 5 | 130+ indicators available |
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
