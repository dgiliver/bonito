# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.9.0] - 2025-12-11 - Agent Chart Control (Phase 3)

### Added
- **Phase 3: Agent Chart Control** - Agent can now manipulate the chart during conversation!
  - `ChartControlTool` - New agent tool for chart manipulation
  - **Add Indicators**: "Add RSI" → RSI(14) appears on chart
  - **Annotations**: "See this candle" → Arrow points to specific bar
  - **Highlights**: "The drawdown period" → Region gets highlighted
  - **Navigate**: "Look at January" → Chart pans to time range
  - **Clear**: "Clear the chart" → Removes all overlays
- **Indicator Overlays**: SMA, EMA, RSI, Bollinger Bands calculated and rendered
- **24 new tests** for ChartControlTool covering all actions
- **Trade Spotlight**: Selected trade now highlighted with gold markers and auto-zoom

### Technical Design
```
┌─────────────┐                    ┌─────────────┐
│    Agent    │◄──── Context ──────│    Chart    │
│             │───── Intents ─────►│             │
└─────────────┘                    └─────────────┘

User: "Add RSI to help me understand oversold"
Agent: [calls chart_control(add_indicator, rsi, {period: 14})]
Chart: RSI(14) panel appears
Agent: "I've added RSI(14). See how entries align with RSI < 30?"
```

### How to Use
The agent now responds to visual requests naturally:
- "Add an SMA to the chart" → SMA overlay appears
- "Highlight March to April" → Region highlighted
- "Point to the entry signal" → Arrow annotation
- "Clear everything" → All overlays removed

### Vision Progress
1. ✅ Context Bridge - Agent knows chart state
2. ✅ Trade Visualization - Trades on chart
3. ✅ **Agent Chart Control** - Agent manipulates chart ← NEW
4. 🔜 Interactive Analysis - Click anywhere → agent explains
5. 🔜 Visual Strategy Building - Draw → agent interprets

---

## [0.8.1] - 2025-12-11 - UI Polish

### Added
- **Quick Action Buttons** in chat panel: Save Strategy, View Trades, Clear Chart, New Chat
- **Trade Navigation** in Trade Details panel: prev/next buttons to browse all trades
- **Buy & Hold Comparison**: Performance bar shows strategy return vs buy & hold with alpha calculation
- **Integration Guide**: `docs/AGENT_CHART_SYNTHESIS.md` - Rules and workflows for adding new chart features

### Fixed
- Chat messages now persist when switching between Chat and Trade Details panels
- Quantity formatting in Trade Details (shows 2-4 decimal places based on value)

---

## [0.8.0] - 2025-12-10 - Visual Language: Agent-Chart Synthesis

### Added
- **F025: Agent-Chart Synthesis** - Revolutionary integration of AI agent and financial charts
  - `AnalysisContext` - Shared state between chart and AI agent
  - `AnalysisView` - Unified view combining Intelligent Chart + Context-Aware Chat
  - `IntelligentChart` - Chart that displays trade markers and responds to clicks
  - `ChartIntent` system - Foundation for agent-controlled chart manipulation
  - Trade markers automatically appear from backtest results
  - Click trade to select and see details in side panel
  - Agent sees chart context (symbol, interval, strategy, selected trade)

### Technical Design
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

### Vision: "The Chart IS the Conversation"
This is Phase 1-2 of a 5-phase roadmap to create a conversational visual analysis experience:
1. ✅ Context Bridge - Agent knows what user is viewing
2. ✅ Trade Visualization - Trades appear on chart
3. 🔜 Agent Chart Control - "Add RSI" → chart updates
4. 🔜 Interactive Analysis - Click anywhere → agent explains
5. 🔜 Visual Strategy Building - Draw → agent interprets

See `docs/VISUAL_LANGUAGE.md` for full technical design.

### Changed
- Default view is now "Analysis" (unified chart + chat)
- Sidebar includes new "Analysis" option with Sparkles icon
- Strategies page remains for legacy backtest workflow

---

## [0.7.0] - 2025-12-10 - UI Virtualization

### Added
- **F024: UI Virtualization & Large Data Handling**
  - `TradeLog` component with virtualized rows (handles 5000+ trades)
  - `VirtualizedMessageList` for chat (handles 200+ messages)
  - `@tanstack/react-virtual` for efficient rendering
  - 41 frontend tests with Vitest + React Testing Library
  - Removed 50-trade limit from API (frontend handles performance)

### Changed
- Strategies page now shows full trade log with virtualization
- Backend returns all trades (no more truncation)
- Added test infrastructure: Vitest, @testing-library/react, jsdom

### Technical
- TDD approach: 41 tests written before implementation
- Virtual rendering: Only visible items rendered to DOM
- Performance: 1000 trades render in <500ms
- All 216 backend tests + 41 frontend tests passing

---

## [0.6.0] - 2025-12-10 - Trailing Stops

### Added
- **F021: Trailing Stops** - Protect profits in trending markets
  - `trailing_stop_pct`: Trail X% below highest price since entry
  - `trailing_atr_multiple`: Trail N × ATR below highest price (volatility-adaptive)
  - `breakeven`: Move stop to entry after profit threshold
- High water mark tracking in position state
- Dynamic stop price calculation per bar
- ATR computation for trailing ATR stops
- Comprehensive test suite for trailing stops (28 tests)

### Changed
- `StopLossType` enum now includes `TRAILING_PERCENT`, `TRAILING_ATR`, `BREAKEVEN`
- `StopLossConfig` has new fields: `atr_period`, `trigger_percent`
- `CreateStrategyTool` accepts `trailing_stop_pct` and `trailing_atr_multiple`
- Agent prompts updated with trailing stop documentation

### Technical
- Engine tracks `highest_price` per position for trailing stops
- Ratchet effect: trailing stop only moves up, never down
- Backward compatible: existing fixed stops work unchanged
- 216 total tests passing

---

## [0.5.0] - 2025-12-10 - pandas-ta Integration

### Added
- **F019: pandas-ta Integration** - 130+ technical indicators now available
  - Volume indicators: VWAP, OBV, CMF, MFI, A/D
  - Trend indicators: ADX (with DI+/DI-), SuperTrend, Aroon, PSAR
  - Volatility/Channels: Donchian Channels, Keltner Channels
  - Momentum: CCI, ROC, Williams %R, Momentum
  - Statistics: Z-Score, Standard Deviation
- Flexible indicator type system (accepts both enum and string types)
- BarData to DataFrame adapter for pandas-ta compatibility
- Multi-column indicator output handling (ADX, Donchian, etc.)
- Comprehensive test suite for pandas-ta indicators (28 tests)

### Changed
- `IndicatorConfig.type` now accepts string indicator names for pandas-ta
- Agent prompts updated with extended indicator documentation
- Parameter mapping: `period` → `length` for pandas-ta compatibility

### Technical
- Lazy loading of pandas-ta to avoid startup overhead
- Backward compatible: all existing strategies work unchanged
- 129 total tests passing

---

## [0.4.2] - 2025-12-02 - Documentation & Planning

### Added
- HIGH_PRIORITY_PLAN.md with detailed implementation analysis
  - pandas-ta integration design
  - Short selling architecture
  - Trailing stops implementation plan
  - Rolling lookback conditions design
  - Plugin interface specification

### Changed
- ARCHITECTURE_V2.md rewritten with current + planned v1.0 architecture
- MVP_ROADMAP.md updated: MVP marked complete, phases 6-10 roadmap added
- PITCH.md refreshed with latest capabilities and business model

---

## [0.4.1] - 2025-12-02 - Strategy Analysis

### Added
- CHANGELOG.md for tracking version history
- Comprehensive strategy architecture limitations analysis in backlog
- Indicator gap analysis (volume, trend strength, channels)
- New feature items: F019 (pandas-ta), F020 (short selling), F021 (trailing stops), F022 (rolling lookback)

### Documentation
- Backlog now includes senior trader perspective on DSL limitations
- Prioritized indicator wishlist with effort estimates
- Recommendation to integrate pandas-ta for 130+ indicators

---

## [0.4.0] - 2025-12-02 - Web UI

### Added
- Next.js web frontend with chat interface
- Real-time SSE streaming for agent responses
- Markdown rendering with `react-markdown`
- Equity curve charting with Recharts
- Strategy management panel (list, view, delete)
- Data panel showing available market data
- Quick action buttons (Save Strategy, Run Backtest, New Chat)
- Sidebar navigation between Chat, Strategies, Data views
- Docker Compose setup for full-stack deployment

### Changed
- FastAPI server now serves both REST API and SSE endpoints
- Agent responses stream incrementally to the UI

---

## [0.3.0] - 2025-11-25 - Agent Integration

### Added
- AI Agent with Claude integration (ReAct loop)
- Tool-calling architecture with structured tool results
- Strategy tools: create, save, load, list strategies
- Backtest tools: run backtests, analyze results
- Data tools: ingest data, list available data, get data info
- Conversation context management
- Agent prompts with system instructions
- Strategy persistence to JSON files in `strategies/` folder
- Multi-timeframe support (1m, 5m, 15m, 1h, 4h, 1d)

### Changed
- CLI now supports `chat` mode for interactive agent sessions
- Strategies can be saved and loaded by name

---

## [0.2.0] - 2025-11-18 - Backtest Engine

### Added
- Vectorized backtest engine with NumPy optimization
- Strategy DSL (Domain Specific Language) using Pydantic models
- Technical indicators: SMA, EMA, RSI, MACD, ATR, Bollinger Bands, Stochastic
- Entry/exit rule conditions with comparisons: gt, gte, lt, lte, eq, crosses_above, crosses_below
- Rule logic: AND/OR combinations
- Position sizing: fixed quantity, fixed value, percent of equity
- Stop loss types: percent, ATR-based, fixed dollar
- Take profit types: percent, ATR-based, fixed dollar, risk multiple
- Performance metrics: Sharpe, Sortino, Calmar, max drawdown, win rate, profit factor
- Equity curve and drawdown tracking
- Commission and slippage modeling
- CLI commands: `backtest` for running backtests

### Changed
- Data models now include typed bar data structures

---

## [0.1.0] - 2025-11-11 - Data Layer

### Added
- Market data ingestion from Yahoo Finance
- DuckDB storage backend for OHLCV data
- Support for multiple timeframes
- CLI interface using Typer
- Commands: `ingest` (download data), `data` (list/info)
- Pydantic models for data validation
- Project structure with `src/bonito/` layout
- Makefile for common operations
- Docker setup (Dockerfile)
- Example strategy JSON files

### Technical
- Python 3.12+ with modern type hints
- Ruff for linting/formatting
- pytest for testing
- uv for dependency management

---

## Version History Summary

| Version | Date | Codename | Key Feature |
|---------|------|----------|-------------|
| 0.5.0 | 2025-12-10 | Indicators | pandas-ta integration, 130+ indicators |
| 0.4.2 | 2025-12-02 | Planning | Architecture, roadmap, high-priority plan |
| 0.4.1 | 2025-12-02 | Analysis | Strategy limitations & indicator gap analysis |
| 0.4.0 | 2025-12-02 | Web UI | Next.js frontend, SSE streaming |
| 0.3.0 | 2025-11-25 | Agent | Claude AI, tool calling, strategy persistence |
| 0.2.0 | 2025-11-18 | Engine | Backtest engine, DSL, indicators |
| 0.1.0 | 2025-11-11 | Foundation | Data layer, Yahoo Finance, DuckDB |
