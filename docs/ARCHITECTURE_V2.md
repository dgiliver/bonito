# Quant Agent v2 Architecture

## Overview

This document outlines the production architecture including strategy persistence, similarity search, web UI, and deployment considerations.

---

## 1. Strategy Store with Similarity Search

### Ideal Flow

```
User: "Create a momentum strategy"
                    │
                    ▼
        ┌───────────────────────┐
        │   Semantic Search     │
        │   (Vector Embeddings) │
        └───────────┬───────────┘
                    │
    ┌───────────────┴───────────────┐
    │                               │
    ▼                               ▼
Found 3 similar strategies     No matches found
    │                               │
    ▼                               ▼
"I found similar strategies:    Create new strategy
 - rsi_momentum (Sharpe: 0.97)    from scratch
 - macd_trend (Sharpe: 0.82)
 Would you like to use one as
 a starting point?"
```

### Strategy Schema

```python
class StrategyRecord(BaseModel):
    """Persisted strategy with metadata."""

    # Identity
    id: str  # UUID
    name: str
    description: str
    version: int = 1

    # Config
    config: StrategyConfig  # The actual DSL config

    # Metadata
    created_at: datetime
    updated_at: datetime
    created_by: str | None  # User ID
    tags: list[str] = []  # ["momentum", "mean-reversion", "trend-following"]

    # Performance (cached from last backtest)
    last_backtest: BacktestSummary | None

    # For similarity search
    embedding: list[float] | None  # Vector embedding of description + config


class BacktestSummary(BaseModel):
    """Cached backtest results for quick display."""

    symbol: str
    period: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    run_at: datetime
```

### Storage Options

| Option | Pros | Cons | Best For |
|--------|------|------|----------|
| **JSON files** | Simple, portable | No search, no concurrency | MVP/Local |
| **SQLite + sqlite-vss** | Single file, vector search | Limited scale | Single-user |
| **PostgreSQL + pgvector** | Full SQL, vector search, scalable | More ops | Production |
| **Supabase** | Managed Postgres + pgvector | Vendor lock-in | Fast deployment |

### Embedding Strategy

```python
def embed_strategy(strategy: StrategyConfig) -> list[float]:
    """Create embedding for similarity search."""

    # Combine textual representation
    text = f"""
    Strategy: {strategy.name}
    Description: {strategy.description}

    Indicators: {', '.join(i.type.value for i in strategy.indicators)}
    Entry logic: {describe_rules(strategy.entry_rules)}
    Exit logic: {describe_rules(strategy.exit_rules)}

    Risk: stop_loss={strategy.stop_loss}, take_profit={strategy.take_profit}
    """

    # Use OpenAI or local embedding model
    return embedding_model.encode(text)
```

---

## 2. Web UI Architecture

### Pages / Views

```
┌─────────────────────────────────────────────────────────────────┐
│  Navigation: [Chat] [Strategies] [Backtests] [Data] [Settings]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                      CHAT VIEW                           │   │
│  │                                                          │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │ Agent: I'll create an RSI momentum strategy...   │    │   │
│  │  │        → create_strategy ✓                       │    │   │
│  │  │        → run_backtest ✓                          │    │   │
│  │  │                                                   │    │   │
│  │  │ Results: 20.3% return, 0.97 Sharpe              │    │   │
│  │  │ [View Details] [Save Strategy] [Compare]         │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  │                                                          │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │ You: Add a trend filter with 100-day SMA        │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  │                                                          │   │
│  │  [Type your message...                        ] [Send]   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    STRATEGIES VIEW                               │
├─────────────────────────────────────────────────────────────────┤
│  [+ New Strategy]  [Import JSON]  Search: [________]            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ rsi_momentum_v2                              Sharpe: 0.97 │  │
│  │ RSI oversold + 100-day SMA trend filter                   │  │
│  │ Tags: [momentum] [trend-filter]                           │  │
│  │ Last tested: SPY (2020-2024) • 20.3% return              │  │
│  │ [Backtest] [Edit] [Clone] [Delete]                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ema_crossover                                Sharpe: 0.39 │  │
│  │ Classic 12/26 EMA crossover                               │  │
│  │ Tags: [crossover] [trend-following]                       │  │
│  │ Last tested: SPY (2022-2024) • 9.96% return              │  │
│  │ [Backtest] [Edit] [Clone] [Delete]                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   BACKTEST DETAIL VIEW                           │
├─────────────────────────────────────────────────────────────────┤
│  Strategy: rsi_momentum_v2  •  Symbol: SPY  •  2020-2024        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐│
│  │                    EQUITY CURVE                             ││
│  │     📈 ────────────────────/\──────/\────────              ││
│  │                          /  \    /  \                       ││
│  │        ─────────────────/    \──/    \──────               ││
│  │   100K                                                      ││
│  │        2020      2021      2022      2023      2024         ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Return      │  │ Sharpe      │  │ Drawdown    │             │
│  │   +20.31%   │  │    0.97     │  │   -8.25%    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│                                                                  │
│  TRADES                                                          │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ Entry      │ Exit       │ Return  │ Reason                  ││
│  │ 2021-09-20 │ 2021-11-08 │ +5.46%  │ RSI overbought          ││
│  │ 2023-08-17 │ 2023-11-01 │ +4.73%  │ RSI overbought          ││
│  └────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Tech Stack Options

| Component | Options | Recommendation |
|-----------|---------|----------------|
| **Frontend** | React, Vue, Svelte, Next.js | **Next.js** (App Router) |
| **Styling** | Tailwind, Chakra, shadcn/ui | **shadcn/ui** + Tailwind |
| **Charts** | Recharts, Chart.js, Lightweight Charts | **Lightweight Charts** (TradingView) |
| **State** | React Query, Zustand, Jotai | **React Query** (server state) |
| **Real-time** | WebSockets, SSE, polling | **SSE** for chat streaming |

---

## 3. API Architecture

### Endpoints

```
POST   /api/chat                    # Send message, stream response
GET    /api/chat/history            # Get conversation history

GET    /api/strategies              # List all strategies
POST   /api/strategies              # Create strategy
GET    /api/strategies/{id}         # Get strategy details
PUT    /api/strategies/{id}         # Update strategy
DELETE /api/strategies/{id}         # Delete strategy
POST   /api/strategies/search       # Semantic search

POST   /api/backtest                # Run backtest
GET    /api/backtest/{id}           # Get backtest results
GET    /api/backtest/{id}/trades    # Get trade list

GET    /api/data/symbols            # List available symbols
POST   /api/data/ingest             # Ingest new data
GET    /api/data/{symbol}/bars      # Get bar data
```

### FastAPI Implementation

```python
# api/main.py
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Quant Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    """Process chat message and stream response."""
    async def generate():
        async for event in agent.process(request.message):
            yield f"data: {event.json()}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/strategies")
async def list_strategies(
    q: str | None = None,  # Semantic search query
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[StrategyRecord]:
    """List strategies with optional search."""
    if q:
        return await strategy_store.semantic_search(q, limit=limit)
    return await strategy_store.list(tags=tags, limit=limit)
```

---

## 4. Deployment Architecture

### Development (Local)

```
┌─────────────────────────────────────────┐
│              Your Machine                │
│                                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │   CLI   │  │   API   │  │   UI    │  │
│  │ (typer) │  │(FastAPI)│  │(Next.js)│  │
│  └────┬────┘  └────┬────┘  └────┬────┘  │
│       │            │            │        │
│       └────────────┼────────────┘        │
│                    │                     │
│            ┌───────┴───────┐             │
│            │    SQLite     │             │
│            │  + DuckDB     │             │
│            └───────────────┘             │
└─────────────────────────────────────────┘
```

### Production (Single-Region)

```
┌──────────────────────────────────────────────────────────────┐
│                         Internet                              │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Cloudflare CDN    │
                    │   (+ WAF, DDoS)     │
                    └──────────┬──────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
    ┌─────────────────┐              ┌─────────────────┐
    │   Next.js UI    │              │   FastAPI       │
    │   (Vercel)      │              │   (Railway)     │
    └─────────────────┘              └────────┬────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
                    ▼                         ▼                         ▼
          ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
          │   PostgreSQL    │      │     Redis       │      │   S3 / R2       │
          │   + pgvector    │      │   (sessions,    │      │   (backtest     │
          │   (Supabase)    │      │    cache)       │      │    results)     │
          └─────────────────┘      └─────────────────┘      └─────────────────┘
```

### Production (High Availability)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Global Load Balancer                             │
│                              (Cloudflare / AWS ALB)                           │
└─────────────────────────────────────┬────────────────────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
              ▼                       ▼                       ▼
    ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
    │   Region: US    │     │   Region: EU    │     │   Region: APAC  │
    │                 │     │                 │     │                 │
    │  ┌───────────┐  │     │  ┌───────────┐  │     │  ┌───────────┐  │
    │  │ API (x3)  │  │     │  │ API (x3)  │  │     │  │ API (x3)  │  │
    │  └─────┬─────┘  │     │  └─────┬─────┘  │     │  └─────┬─────┘  │
    │        │        │     │        │        │     │        │        │
    │  ┌─────┴─────┐  │     │  ┌─────┴─────┐  │     │  ┌─────┴─────┐  │
    │  │  PG Read  │  │     │  │  PG Read  │  │     │  │  PG Read  │  │
    │  │  Replica  │  │     │  │  Replica  │  │     │  │  Replica  │  │
    │  └───────────┘  │     │  └───────────┘  │     │  └───────────┘  │
    └─────────────────┘     └─────────────────┘     └─────────────────┘
              │                       │                       │
              └───────────────────────┼───────────────────────┘
                                      │
                                      ▼
                           ┌─────────────────┐
                           │  PG Primary     │
                           │  (US region)    │
                           └─────────────────┘
```

---

## 5. Resilience Patterns

### API Resilience

```python
# Circuit breaker for LLM calls
from tenacity import retry, stop_after_attempt, wait_exponential

class ResilientLLMClient:
    def __init__(self, primary: LLMClient, fallback: LLMClient | None = None):
        self.primary = primary
        self.fallback = fallback
        self.circuit_open = False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def chat(self, messages: list[Message], **kwargs) -> Message:
        try:
            return await self.primary.chat(messages, **kwargs)
        except Exception as e:
            if self.fallback:
                logger.warning(f"Primary LLM failed, using fallback: {e}")
                return await self.fallback.chat(messages, **kwargs)
            raise
```

### Backtest Queue

```python
# Use Redis + Celery for long-running backtests
from celery import Celery

celery_app = Celery("quant_agent", broker="redis://localhost:6379/0")

@celery_app.task(bind=True, max_retries=3)
def run_backtest_task(self, strategy_id: str, config: dict) -> str:
    """Run backtest in background."""
    try:
        result = engine.run(...)
        save_result(result)
        return result.id
    except Exception as e:
        self.retry(exc=e, countdown=60)
```

### Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/chat")
@limiter.limit("10/minute")  # 10 chat messages per minute
async def chat(request: Request, body: ChatRequest):
    ...

@app.post("/api/backtest")
@limiter.limit("5/minute")  # 5 backtests per minute
async def backtest(request: Request, body: BacktestRequest):
    ...
```

---

## 6. Implementation Priority

### Phase 1: Strategy Persistence (This Week)
```
1. [ ] Add strategy save/load to disk (JSON)
2. [ ] Add save_strategy tool for agent
3. [ ] Add load_strategy tool for agent
4. [ ] CLI commands: quant strategy list/save/load
```

### Phase 2: API + Basic UI (Next 2 Weeks)
```
1. [ ] FastAPI server with core endpoints
2. [ ] Next.js app with chat interface
3. [ ] Strategy library view
4. [ ] Basic backtest results display
```

### Phase 3: Similarity Search (Week After)
```
1. [ ] Add embeddings to strategy records
2. [ ] Implement semantic search
3. [ ] Integrate with agent ("I found similar strategies...")
```

### Phase 4: Production Hardening
```
1. [ ] Add PostgreSQL support
2. [ ] Implement rate limiting
3. [ ] Add authentication (Clerk/Auth0)
4. [ ] Deploy to Railway/Vercel
5. [ ] Add monitoring (Sentry, PostHog)
```

---

## Quick Start: Strategy Persistence

Let's implement Phase 1 now:

```python
# src/quant_agent/storage/strategies.py

class StrategyStore:
    """Persistent strategy storage."""

    def __init__(self, base_dir: Path = Path("strategies")):
        self.base_dir = base_dir
        self.base_dir.mkdir(exist_ok=True)

    def save(self, strategy: StrategyConfig, backtest_result: BacktestResult | None = None) -> str:
        """Save strategy to disk."""
        record = StrategyRecord(
            id=str(uuid.uuid4()),
            name=strategy.name,
            description=strategy.description,
            config=strategy,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_backtest=BacktestSummary.from_result(backtest_result) if backtest_result else None,
        )

        path = self.base_dir / f"{strategy.name}.json"
        path.write_text(record.model_dump_json(indent=2))
        return record.id

    def load(self, name: str) -> StrategyRecord | None:
        """Load strategy by name."""
        path = self.base_dir / f"{name}.json"
        if not path.exists():
            return None
        return StrategyRecord.model_validate_json(path.read_text())

    def list(self) -> list[StrategyRecord]:
        """List all saved strategies."""
        strategies = []
        for path in self.base_dir.glob("*.json"):
            strategies.append(StrategyRecord.model_validate_json(path.read_text()))
        return sorted(strategies, key=lambda s: s.updated_at, reverse=True)

    def search(self, query: str) -> list[StrategyRecord]:
        """Simple text search (upgrade to vector search later)."""
        query_lower = query.lower()
        results = []
        for strategy in self.list():
            if (query_lower in strategy.name.lower() or
                query_lower in strategy.description.lower()):
                results.append(strategy)
        return results
```

---

*Ready to implement? Start with strategy persistence, then build up from there.*
