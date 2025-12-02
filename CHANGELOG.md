# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
| 0.4.1 | 2025-12-02 | Analysis | Strategy limitations & indicator gap analysis |
| 0.4.0 | 2025-12-02 | Web UI | Next.js frontend, SSE streaming |
| 0.3.0 | 2025-11-25 | Agent | Claude AI, tool calling, strategy persistence |
| 0.2.0 | 2025-11-18 | Engine | Backtest engine, DSL, indicators |
| 0.1.0 | 2025-11-11 | Foundation | Data layer, Yahoo Finance, DuckDB |
