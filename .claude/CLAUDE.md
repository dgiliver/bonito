# Bonito - Claude Code Configuration

> AI-native algorithmic trading platform: backtesting and deployment built for agents, not scripts.

## Quick Commands

```bash
# Development
make api              # Start API server (port 8000)
make web              # Start frontend (port 3000)
make chat             # CLI agent chat
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
```

## Project Structure

```
src/bonito/
├── agent/          # LLM agent (Claude integration, orchestrator, tools)
├── backtest/       # Vectorized backtest engine, indicators, strategy DSL
├── data/           # DuckDB market data storage
├── tools/          # Agent tools (backtest, data, strategy, chart control)
├── api/            # FastAPI REST API with SSE streaming
└── cli.py          # Typer CLI

web/                # Next.js 16 frontend (React 19, TypeScript, lightweight-charts)
tests/              # pytest test suite
docs/               # Architecture, roadmaps, design docs
strategies/         # Example strategy JSON files
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
- Pre-commit hooks run: ruff, mypy, ESLint, Prettier, TypeScript checks

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
| `src/bonito/tools/` | All agent tools |
| `web/src/components/analysis/` | Chart components, indicator panels |
| `web/src/contexts/AnalysisContext.tsx` | Chart state management |

## Current State (v0.9.1)

**Completed:**
- MVP (Phases 0-5): data layer, backtest engine, tools, agent, API, frontend
- Phase 3 post-MVP: Agent chart control, trade spotlight, crosshair labels
- pandas-ta integration (60+ indicators)
- Trailing stops (percent and ATR-based)
- F020: Short selling support ✅
- F022: Rolling lookback conditions ✅
- F002: Strategy plugin interface ✅
- Dynamic panel ordering (panels render in user add order)
- Panel re-initialization fix (panels survive height changes)

**In Progress:**
- Drawing tools (trendlines, annotations) - see `drawing-tools` agent
- Additional indicator panels (ADX, CCI, ATR)

**Next Up:**
- Authentication (Supabase)
- Real-time data (WebSocket price feeds)
- Production deployment

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
| `/backtest` | Run and analyze backtests |
| `/tdd` | Test-Driven Development cycle |
| `/ralph` | Autonomous development loops |
| `/commit` | Proper git commit formatting |
| `/review` | Code review before commit |
| `/explore-ui` | Start servers and explore UI |

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
1. /verify-ui                      # Quick check
2. Use ui-explorer agent           # Detailed exploration
3. Use chart-validator agent       # Comprehensive validation
```
