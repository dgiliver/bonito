# Bonito - Claude Code Configuration

> AI-native algorithmic trading platform: backtesting and deployment built for agents, not scripts.

## Quick Commands

```bash
# Development
make api              # Start API server (port 8000)
make web              # Start frontend (port 3000)
make dashboard        # Live-trading dashboard, read-only (port 8050)
make chat             # CLI agent chat
make research         # Run autonomous strategy research (SPY, 1000 iterations)
make ingest-universe  # Ingest 33-symbol universe into DuckDB
make test             # Run all tests
make test-fast        # Skip slow tests
make lint             # Run ruff linter
make format           # Auto-format code
make typecheck        # Run mypy

# Docker
make docker-up        # Start all containers
make docker-down      # Stop containers

# Data
bonito ingest SPY AAPL --start 2020-01-01 --end 2024-12-01

# Live trading pipeline (paper or live)
bonito live refresh [-u config/universe.live.json]       # Pull latest price data
bonito live preflight [-u config/universe.live.json]     # Fail-closed gate (kill switch, flags, data)
bonito live run [--no-refresh] [-u ...]                  # Generate intents; auto-fills in paper mode
bonito live reconcile '<{"SYMBOL":qty}>' [-u ...]        # Check broker positions vs ledger
bonito live record-fill SYMBOL buy PRICE --dollars N --broker-order-id ID  # Record a live fill
bonito live status [-u ...]                              # Print current positions + P&L
bonito live sweep [--execute] [-u ...]                   # Intraday stop sweep
bonito live stop-levels [-u ...]                         # Per-position stop/TP price, for broker-side GTC orders
bonito live tracking [-u ...]                            # Paper-vs-replay fidelity check
bonito live backtest-universe [-u ...]                   # Per-symbol strategy validation
bonito live backtest-account [-u ...]                    # Full account-level replay

# Strategy research
bonito research auto [--apply] [-u ...]                  # Weekly: rolling holdout, graded bundles, sync live config
bonito research clusters [--per-symbol] [--apply] [-u ...]  # One-shot cluster search
```

## Project Structure

```
src/bonito/
├── agent/          # LLM agent (Claude integration, orchestrator, tools)
├── backtest/       # Vectorized backtest engine, indicators, strategy DSL
├── data/           # DuckDB market data storage
├── research/       # Strategy research: cluster search + autonomous weekly loop
├── trading/        # Live trading pipeline (runner, portfolio backtest, tracking)
├── tools/          # Agent tools (backtest, data, strategy, chart control)
├── api/            # FastAPI REST API with SSE streaming
└── cli.py          # Typer CLI

web/                # Next.js 16 frontend (React 19, TypeScript, lightweight-charts)
tests/              # pytest test suite
docs/               # Architecture, roadmaps, design docs
strategies/         # JSON strategy configs (deployed + per-symbol)
config/             # universe.json (paper) + universe.live.json (live, mode/live_enabled human-only)
livetrade/          # Paper ledger, live ledger, intents, and research artifacts (git-tracked)
.github/workflows/  # paper-trading, intraday-stops, weekly-research CI
```

## Code Style

### Python (Backend)
- Python 3.12+, use modern typing (`list[str]` not `List[str]`)
- Pydantic v2 for all models and validation
- Async/await for all I/O operations
- 100-character line limit (configured in ruff)
- Use `ruff format` before committing

### TypeScript (Frontend)
- React 19 with functional components and hooks
- Use `interface` for object shapes, `type` for unions/aliases
- Tailwind CSS for styling (no CSS modules)
- ESLint 9 configured in `eslint.config.mjs`

### Commits
- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`
- Run `make pre-commit` before committing
- Pre-commit hooks run: ruff, ESLint, Prettier, TypeScript checks (blocking); mypy runs too but is advisory/report-only — it never blocks a commit

## Architecture Decisions

### Strategy DSL (not arbitrary Python)
Strategies are JSON-serializable configs - NOT Python code:
```json
{
  "indicators": [{"type": "sma", "name": "sma_20", "params": {"period": 20}}],
  "entry_rules": [{"conditions": [{"left": "close", "comparison": "crosses_above", "right": "sma_20"}]}],
  "exit_rules": [...],
  "position_size": {"type": "percent_equity", "value": 10},
  "stop_loss": {"type": "percent", "value": 0.05}
}
```

### Vectorized Backtesting
- All indicator calculations use NumPy arrays (not bar-by-bar)
- Sub-second execution for typical strategies
- No arbitrary code execution - full auditability

### Tool Protocol (MCP-style)
Tools in `src/bonito/tools/` implement:
- `name`, `description`, `parameters` (JSON Schema)
- `async execute(**kwargs) -> ToolResult`

### Chart-Agent Synthesis
- `AnalysisContext` is single source of truth for chart state
- Agent sends `ChartIntent` commands to control visualization
- Bidirectional: agent sees what user views, controls chart display

## Testing

```bash
pytest tests/                           # All tests
pytest tests/test_backtest_engine.py    # Specific file
pytest -k "test_rsi"                    # By name pattern
pytest -m "not slow"                    # Skip slow tests
```

Test files:
- `tests/test_backtest_engine.py` - Core backtest logic
- `tests/test_indicators.py` - Technical indicator calculations
- `tests/test_strategy.py` - Strategy DSL validation
- `tests/test_data_store.py` - DuckDB operations

## Key Files to Know

| File | Purpose |
|------|---------|
| `src/bonito/agent/orchestrator.py` | ReAct loop, system prompt, event streaming |
| `src/bonito/backtest/engine.py` | Vectorized backtest execution |
| `src/bonito/backtest/indicators.py` | All technical indicators (SMA, RSI, MACD, pandas-ta) |
| `src/bonito/backtest/strategy.py` | Strategy DSL Pydantic models |
| `src/bonito/research/autoresearch_trading.py` | Karpathy-style autonomous strategy mutation loop |
| `src/bonito/research/auto_research.py` | Weekly rolling-holdout + graded-bundle adoption loop |
| `src/bonito/research/cluster_research.py` | Cluster / per-symbol grid search (450 EMA candidates; opt-in ADX/MACD/BBands templates via `--templates`) |
| `src/bonito/research/regime_sweep.py` | Slices one backtest into fixed historical regimes (GFC/COVID/2022 bear/AI bull) vs. buy-and-hold — `bonito research regime-sweep <strategy.json>` |
| `src/bonito/trading/live_runner.py` | Intent generation, risk caps, kill switch, preflight |
| `src/bonito/trading/portfolio_backtest.py` | Account-level replay (ReplayStore, strategy attribution) |
| `src/bonito/trading/tracking.py` | Paper-vs-replay fidelity (fill gaps, equity drift) |
| `src/bonito/tools/` | All agent tools |
| `web/src/components/analysis/` | Chart components, indicator panels |
| `web/src/contexts/AnalysisContext.tsx` | Chart state management |
| `config/universe.json` | Paper trading config (33 symbols, 8 slots, dynamic sizing) |
| `config/universe.live.json` | Live config — synced by research; mode/live_enabled human-only |
| `docs/EXPERIMENT_LOG.md` | Canonical record of adopted/rejected optimizations |
| `docs/AUTONOMOUS_LIVE_ROUTINE.md` | How to run the live cycle unattended via Claude Routines |
| `tasks/todo.md` | Pre-live checklist + current task tracking |
| `tasks/lessons.md` | Hard-won lessons (prevent repeated mistakes) |

## Current State (v1.0 — Autonomous Trading)

**Core platform (complete):**
- MVP (Phases 0-5): data layer, backtest engine, tools, agent, API, frontend
- Agent chart control, trade spotlight, crosshair labels
- pandas-ta integration (60+ indicators)
- Trailing stops (percent and ATR-based), short selling, rolling lookback conditions
- Dynamic panel ordering; panel re-initialization fix

**Live trading pipeline (complete):**
- Paper + live ledger, intent-based execution (sells-before-buys), kill switch (25% drawdown halt)
- Dynamic position sizing: `position_pct_equity` scales slots with equity; $2,500 hard cap
- 33-symbol universe, 8 slots, per-symbol strategies (AAPL/GOOGL/IREN assigned)
- Entry blocklist (`entry_blocklist`) for benched symbols; exits never gated
- `bonito live preflight`: fail-closed gate (kill switch, flag mismatch, total data outage)
- `bonito live tracking`: paper-vs-replay fidelity (fill bps gap, decision divergences, equity drift)
- `bonito live backtest-account`: full account-level replay; structurally prevents look-ahead

**Autonomous research (complete):**
- Weekly rolling-holdout research (`bonito research auto --apply`) — runs unattended every Saturday
- Per-symbol grid search: 450 candidates (extended from 144); profitable-holdout gate
- Graded fallback bundles: (swap+assignments+bench) → ... → assignments-only; first passing ships
- Grid-edge flags: winners at search boundary surfaced in digest as human cue to extend
- `sync_live_config()`: mirrors validated structure into universe.live.json; NEVER touches mode/live_enabled/risk caps
- Experiment log (`docs/EXPERIMENT_LOG.md`) — canonical record of adopted/rejected optimizations; pre-register criterion before running

**Autonomous execution (complete):**
- GitHub Actions: paper shadow daily + intraday stop sweeps (never real orders)
- Claude Code Routine: scheduled live cycle (reconcile → preflight → run → place → record → commit)
- Robinhood MCP wired as claude.ai connector; Agentic account (••••8597) only
- Broker-side GTC stop orders: intraday protection 24/7 without a running session

**In progress / next:**
- Drawing tools (trendlines, annotations)
- ≥2 weeks paper-vs-replay tracking OK → user sign-off → flip live_enabled (see `tasks/todo.md`)

## Agent & Skill Architecture

Bonito uses a comprehensive swarm architecture for development:

### Specialized Agents (`.claude/agents/`)
| Agent | Purpose |
|-------|---------|
| `indicator-builder` | Create new technical indicators (backend + frontend) |
| `chart-validator` | Visual verification of chart rendering and sync |
| `drawing-tools` | Implement chart annotations without breaking charts |
| `frontend-dev` | React/Next.js/TypeScript UI work |
| `ui-explorer` | Autonomous UI testing via Chrome MCP |
| `backtest-analyst` | Analyze strategy performance metrics |
| `tdd-developer` | Test-Driven Development for features |
| `debugger` | Systematic bug investigation |
| `performance-optimizer` | Profile and optimize slow code |

### Skills (`.claude/skills/`)
| Skill | Usage |
|-------|-------|
| `/panel-test` | Comprehensive indicator panel testing |
| `/add-indicator` | Streamlined indicator addition workflow |
| `/verify-ui` | Quick visual verification after changes |
| `/playwright-test` | Three-agent headless testing (validation, edge-case, stress) |
| `/backtest` | Run and analyze backtests |
| `/tdd` | Test-Driven Development cycle |
| `/ralph` | Autonomous development loops |
| `/commit` | Proper git commit formatting |
| `/review` | Code review before commit |
| `/explore-ui` | Start servers and explore UI |
| `/autoresearch` | Karpathy-style autonomous iteration loop (any metric) |
| `/robinhood-trade` | Daily trading cycle or intraday sweep via Robinhood MCP |

### Ralph Wiggum Loops
For autonomous iterative development:
```bash
/ralph-loop "Task description with clear completion criteria
- Step 1
- Step 2
- Verification: make test
Output <promise>DONE</promise>" --max-iterations 20
```

## Documentation

All detailed docs in `/docs/`:
- `ARCHITECTURE.md` - System design overview
- `MVP_ROADMAP.md` - Development phases
- `HIGH_PRIORITY_PLAN.md` - Detailed feature implementation plans
- `AGENT_CHART_SYNTHESIS.md` - Chart-agent integration rules
- `LAUNCH_PLAN.md` - Go-to-market strategy
- `EXPERIMENT_LOG.md` - Adopted/rejected optimization registry (pre-register before running)
- `AUTONOMOUS_LIVE_ROUTINE.md` - How to run the live cycle unattended via Claude Code Routines

## Environment

Required env vars in `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...   # Required
OPENAI_API_KEY=sk-...          # Optional (for OpenAI models)
LOG_LEVEL=INFO                 # DEBUG for verbose
```

## Gotchas

1. **pandas-ta returns DataFrames** - Always extract `.values` for NumPy arrays
2. **Multi-column indicators** (ADX, MACD) return `{name}_{suffix}` columns
3. **DuckDB is in `data/market_data.duckdb`** - Don't delete without re-ingesting
4. **Frontend uses App Router** - Not Pages Router
5. **lightweight-charts requires client-side only** - Use dynamic imports with `ssr: false`
6. **Strategy configs are JSON** - Not Python, no code execution

## Critical Frontend Patterns

### Panel Component State Management
**CRITICAL**: Always use React state for crosshair-updated values:
```tsx
const [currentValue, setCurrentValue] = useState<number | null>(null);

// In syncCrosshair:
if (data.time && panelRef.current) {
  setCurrentValue(panelRef.current.getLegendData(data.time).value);
}
```
Without this, panel data disappears when cursor moves.

### Panel Initialize useEffect
**CRITICAL**: Use `[height, config]` as dependencies, NOT `[]`:
```tsx
useEffect(() => {
  if (containerRef.current && panelRef.current) {
    panelRef.current.initialize(containerRef.current);
  }
}, [height, config]); // NOT []
```
Empty deps cause panel to not re-initialize when height changes (new panels added).

This `[height, config]` recreate-on-resize pattern applies to **`panels/`** components
(`RSIPanel.tsx`, `MACDPanel.tsx`, `StochasticPanel.tsx`) — they destroy and recreate
their chart instance when height changes.

**`charts/`** components (`PanelChartPanel.tsx`, `PriceChartPanel.tsx`) intentionally use
a DIFFERENT pattern instead: their init `useEffect` excludes height from its deps, and a
separate resize `useEffect` calls `.resize()` on the existing chart instance when height
changes, rather than destroying/recreating it. This avoids visual thrash on every height
change. This is intentional, not a bug — do not "fix" `charts/` components by copying the
`panels/` recreate-on-resize pattern.

### Dynamic Panel Rendering
Panels must render in user add order via `activePanels.map()`:
```tsx
{activePanels.map((panel, index) => {
  const isLastPanel = index === activePanels.length - 1;
  const showTimeScale = isLastPanel;
  // switch on panel.type
})}
```

## Known Gaps (To Implement)

### Not Yet Implemented
- **Drawing Tools**: No trendlines, horizontal levels, or annotations
- **Chart Persistence**: Drawings don't save across sessions
- **Keyboard Shortcuts**: No hotkeys for common actions
- **Mobile Touch**: Limited touch event support
- **Real-time Data**: WebSocket feeds not connected
- **E2E Tests**: Playwright tests not comprehensive

### Architecture Debt
- Agent intent system partially complete (annotate, highlight work; others pending)
- No drawing manager in ChartContainer
- Missing localStorage persistence layer for UI state

## Autonomous Trading Stack

The system runs with zero daily intervention once live:

| Layer | Mechanism | Frequency | Human touch |
|-------|-----------|-----------|-------------|
| **Paper shadow** | GitHub Actions (`paper-trading.yml`) | Daily 3:50pm ET | None |
| **Intraday stops** | GitHub Actions (`intraday-stops.yml`) | Every 15 min, 9:30–16:00 ET | None |
| **Weekly research** | GitHub Actions (`weekly-research.yml`) | Saturday 13:00 UTC | GitHub issue on adoption/rejection |
| **Live cycle** | Claude Code Routine (`/schedule weekdays at 3:45pm ET`) | Daily 3:45pm ET | None after sign-off |
| **Intraday live stops** | Broker-side GTC stop orders | 24/7 | Cancel/replace daily via Routine |

**Human-only controls (never automated):**
- `mode` and `live_enabled` in `config/universe.live.json`
- Risk caps (`max_position_usd`, `position_pct_equity`, `max_positions`)
- `bonito live resume` after a kill-switch halt
- Creating the Routine (`/schedule` from a local Claude Code terminal)

**Pre-live checklist:** `tasks/todo.md` — gated on ≥2 weeks paper-vs-replay tracking OK + explicit sign-off.

## Recommended Swarms by Task

### Adding New Indicator
```
1. /add-indicator panel <name>     # Follow patterns
2. /panel-test <name>              # Test solo
3. /panel-test <name> --then macd  # Test combination
4. /verify-ui panels               # Visual check
5. /commit                         # Commit changes
```

### Fixing Chart Bug
```
1. Use debugger agent              # Investigate root cause
2. /tdd "fix description"          # Write test first
3. /panel-test --full-matrix       # Verify no regressions
4. /verify-ui                      # Visual confirmation
5. /review && /commit              # Review and commit
```

### Implementing New Feature
```
1. Use architect agent             # Design approach
2. /tdd "feature description"      # TDD implementation
3. Use chart-validator agent       # Visual verification
4. /panel-test --full-matrix       # Full panel testing
5. /review && /commit              # Review and commit
```

### Visual Verification After Changes
```
1. /verify-ui                      # Quick manual check
2. /playwright-test                # Full 3-agent headless sweep (validation + edge + stress)
3. /playwright-test validation     # Just correctness checks
4. /playwright-test edge           # Just boundary conditions
5. /playwright-test stress         # Just performance profiling
```

### Documentation Updates
```
1. Use doc-writer agent            # Follow doc patterns
2. /doc-cleanup --audit            # Check for staleness
3. /doc-cleanup --consolidate      # Merge redundant docs
```

### Live Trading Cycle
```
1. /robinhood-trade daily          # Full daily cycle (paper or live)
2. /robinhood-trade monitor        # One intraday stop sweep
3. bonito live tracking            # Paper-vs-replay fidelity
4. bonito live backtest-account    # Account replay after any pipeline change
```

### Strategy Optimization
```
1. Read docs/EXPERIMENT_LOG.md     # Check what's already been tried
2. Pre-register criterion          # train+holdout both must improve
3. bonito research clusters --per-symbol --apply  # One-shot per-symbol grid
4. bonito research auto --apply    # Full weekly research pass
5. Log outcome in EXPERIMENT_LOG.md (adopted OR rejected — both matter)
```

## MCP Integrations

### Active
| Plugin | Purpose | Notes |
|--------|---------|-------|
| **Robinhood MCP** | Live order execution | Connected as claude.ai connector; Agentic account only (••••8597) |
| **GitHub MCP** | Issue/PR visibility | Weekly research opens issues on adoption/rejection/tracking WARN |

### Future
| Plugin | Purpose | Why |
|--------|---------|-----|
| **Alpha Vantage MCP** | Real-time market data | Better than Yahoo Finance for live data |
| **Financial Datasets MCP** | Fundamentals | Income statements, balance sheets for factor strategies |
| **Memory MCP** | Persistent knowledge | Remember user preferences, past strategies |
| **PostgreSQL MCP** | Production database | When moving beyond DuckDB |

### State-of-the-Art Setup Recommendations
1. **Git worktrees** - Each Claude session in isolated checkout
2. **Subagents for research** - Spawn explore agents for codebase search
3. **Planning mode** - For any feature >3 files changed
4. **Claude Opus 4.6** - For complex architectural decisions
5. **Parallel tool calls** - Group independent operations

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness
- Use Python LSP (`pylsp`) for go-to-definition, find-references, hover, and diagnostics before refactoring

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
- **LSP-Informed Refactoring**: Before renaming, moving, or refactoring Python code, use the Python LSP to find all references and dependents. Don't guess — verify via `findReferences` and `goToDefinition`.

## Python LSP Integration

Python Language Server (`pylsp`) is configured globally for all Bonito sessions. Use LSP operations to:
- **Find references** before renaming or removing functions/classes
- **Go to definition** to understand call chains before modifying
- **Get diagnostics** to catch type errors and undefined names
- **Hover** for quick type information on complex expressions
- This replaces guesswork with certainty when refactoring across `src/bonito/`
