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
**Effort**: 1 week
**Value**: High - Real portfolio strategies

Support strategies that trade multiple symbols with:
- Portfolio-level position sizing
- Correlation-aware allocation
- Sector exposure limits

---

### F007: Live Paper Trading
**Status**: Backlog
**Effort**: 2 weeks
**Value**: High - Validate in real-time

Connect to broker API (Alpaca) for paper trading:
- Real-time data feed
- Order execution simulation
- Performance tracking

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

## 🟢 Nice to Have (Future)

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

---

*Last updated: Week 4 - API Server*
