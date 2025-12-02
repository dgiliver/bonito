# Architecture Diagrams

Detailed multi-user flow charts and architecture diagrams for Bonito.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         INTERNET                                                     │
└───────────────────────────────────────────┬─────────────────────────────────────────────────────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    CLOUDFLARE (CDN + DNS)                                            │
│                                      yourdomain.com                                                  │
└───────────────────────────────────────────┬─────────────────────────────────────────────────────────┘
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    │                                               │
                    ▼                                               ▼
┌───────────────────────────────────────┐       ┌───────────────────────────────────────┐
│           VERCEL (Frontend)            │       │          RAILWAY (Backend)            │
│                                        │       │                                        │
│  ┌──────────────────────────────────┐ │       │  ┌──────────────────────────────────┐ │
│  │         Next.js App               │ │       │  │         FastAPI Server           │ │
│  │                                   │ │       │  │                                   │ │
│  │  • Landing Page                   │ │       │  │  • /api/chat (SSE streaming)     │ │
│  │  • Auth Pages (login/signup)      │ │       │  │  • /api/strategies (CRUD)        │ │
│  │  • Dashboard                      │ │       │  │  • /api/backtest (run tests)     │ │
│  │  • Chat Interface                 │ │       │  │  • /api/data (ingest + query)    │ │
│  │  • Strategy Manager               │ │       │  │                                   │ │
│  │  • Equity Charts                  │ │       │  │  ┌─────────────────────────────┐ │ │
│  │                                   │ │       │  │  │    Backtest Engine          │ │ │
│  │  ┌─────────────────────────────┐ │ │       │  │  │    • pandas-ta (130+ ind)   │ │ │
│  │  │  Supabase Client            │ │ │       │  │  │    • NumPy vectorized       │ │ │
│  │  │  • Auth state               │ │ │       │  │  │    • Strategy DSL           │ │ │
│  │  │  • Session management       │ │ │       │  │  └─────────────────────────────┘ │ │
│  │  │  • JWT tokens               │ │ │       │  │                                   │ │
│  │  └─────────────────────────────┘ │ │       │  │  All user data fetched from      │ │
│  └──────────────────────────────────┘ │       │  │  Supabase (RLS enforced)         │ │
│                                        │       │  │                                   │ │
└───────────────────────────────────────┘       │  └──────────────────────────────────┘ │
                    │                            └───────────────────────────────────────┘
                    │                                               │
                    │                                               │
                    └───────────────────┬───────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         SUPABASE                                                     │
│  ┌─────────────────────────────────────────┐  ┌─────────────────────────────────────────┐          │
│  │              AUTH SERVICE               │  │            POSTGRESQL                    │          │
│  │                                         │  │                                          │          │
│  │  • Email/Password signup                │  │  ┌────────────────────────────────────┐ │          │
│  │  • Google OAuth                         │  │  │         auth.users                 │ │          │
│  │  • Session management                   │  │  │  • id (UUID)                       │ │          │
│  │  • JWT token generation                 │  │  │  • email                           │ │          │
│  │  • Password reset                       │  │  │  • created_at                      │ │          │
│  │                                         │  │  └────────────────────────────────────┘ │          │
│  └─────────────────────────────────────────┘  │           │          │          │       │          │
│                                                │           │ FK       │ FK       │ FK    │          │
│  ┌─────────────────────────────────────────┐  │           ▼          ▼          ▼       │          │
│  │          ROW LEVEL SECURITY             │  │  ┌────────────┐ ┌────────────┐ ┌──────────────┐   │
│  │                                         │  │  │ market_data│ │ strategies │ │conversations │   │
│  │  auth.uid() = user_id                   │  │  │            │ │            │ │              │   │
│  │                                         │  │  │ • user_id  │ │ • user_id  │ │ • user_id    │   │
│  │  User A can only see User A's data      │  │  │ • symbol   │ │ • name     │ │ • title      │   │
│  │  User B can only see User B's data      │  │  │ • timeframe│ │ • config   │ │ • messages   │   │
│  │                                         │  │  │ • OHLCV    │ │ • backtest │ │              │   │
│  │  Applies to ALL tables:                 │  │  │            │ │            │ │              │   │
│  │  • market_data                          │  │  │ RLS ✓      │ │ RLS ✓      │ │ RLS ✓        │   │
│  │  • strategies                           │  │  └────────────┘ └────────────┘ └──────────────┘   │
│  │  • conversations                        │  │                                          │          │
│  └─────────────────────────────────────────┘  └─────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                      ANTHROPIC API                                                   │
│                                    Claude Sonnet (LLM)                                               │
│                                                                                                      │
│  • Strategy generation from natural language                                                         │
│  • Result interpretation and suggestions                                                             │
│  • Tool calling (create_strategy, run_backtest, etc.)                                               │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## User Authentication Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    NEW USER SIGNUP FLOW                                               │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────┐                    ┌─────────┐                    ┌─────────┐
    │  USER   │                    │ VERCEL  │                    │SUPABASE │
    │(Browser)│                    │(Next.js)│                    │ (Auth)  │
    └────┬────┘                    └────┬────┘                    └────┬────┘
         │                              │                              │
         │  1. Visit /signup            │                              │
         │─────────────────────────────▶│                              │
         │                              │                              │
         │  2. Render Auth UI           │                              │
         │◀─────────────────────────────│                              │
         │                              │                              │
         │  3. Enter email + password   │                              │
         │      OR click "Google"       │                              │
         │─────────────────────────────▶│                              │
         │                              │                              │
         │                              │  4. supabase.auth.signUp()   │
         │                              │─────────────────────────────▶│
         │                              │                              │
         │                              │                              │  5. Create user in
         │                              │                              │     auth.users table
         │                              │                              │     Generate JWT
         │                              │                              │
         │                              │  6. Return session + JWT     │
         │                              │◀─────────────────────────────│
         │                              │                              │
         │  7. Store session in         │                              │
         │     localStorage/cookie      │                              │
         │◀─────────────────────────────│                              │
         │                              │                              │
         │  8. Redirect to /dashboard   │                              │
         │◀─────────────────────────────│                              │
         │                              │                              │
    ┌────┴────┐                    ┌────┴────┐                    ┌────┴────┐
    │  USER   │                    │ VERCEL  │                    │SUPABASE │
    └─────────┘                    └─────────┘                    └─────────┘


┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   RETURNING USER LOGIN FLOW                                           │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────┐                    ┌─────────┐                    ┌─────────┐
    │  USER   │                    │ VERCEL  │                    │SUPABASE │
    └────┬────┘                    └────┬────┘                    └────┬────┘
         │                              │                              │
         │  1. Visit /login             │                              │
         │─────────────────────────────▶│                              │
         │                              │                              │
         │  2. Enter credentials        │                              │
         │─────────────────────────────▶│                              │
         │                              │                              │
         │                              │  3. supabase.auth.signIn()   │
         │                              │─────────────────────────────▶│
         │                              │                              │
         │                              │                              │  4. Validate credentials
         │                              │                              │     Generate new JWT
         │                              │                              │
         │                              │  5. Return session + JWT     │
         │                              │◀─────────────────────────────│
         │                              │                              │
         │  6. Redirect to /dashboard   │                              │
         │◀─────────────────────────────│                              │
         │                              │                              │


┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    SESSION VALIDATION (Every Request)                                 │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────┐                    ┌─────────┐                    ┌─────────┐
    │  USER   │                    │ VERCEL  │                    │SUPABASE │
    └────┬────┘                    └────┬────┘                    └────┬────┘
         │                              │                              │
         │  1. Request any page         │                              │
         │     (with session cookie)    │                              │
         │─────────────────────────────▶│                              │
         │                              │                              │
         │                              │  2. Middleware checks        │
         │                              │     supabase.auth.getSession │
         │                              │─────────────────────────────▶│
         │                              │                              │
         │                              │  3. Valid session? ──────────┤
         │                              │◀─────────────────────────────│
         │                              │                              │
         │                              │  ┌─────────────────────────┐ │
         │                              │  │ If valid: continue      │ │
         │                              │  │ If invalid: → /login    │ │
         │                              │  └─────────────────────────┘ │
         │                              │                              │
         │  4. Render page              │                              │
         │◀─────────────────────────────│                              │
         │                              │                              │
```

---

## Chat/Backtest Request Flow (Authenticated)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            USER SENDS CHAT MESSAGE (e.g., "Create an RSI strategy")                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────┐        ┌─────────┐        ┌─────────┐        ┌─────────┐        ┌─────────┐
│  USER   │        │ VERCEL  │        │ RAILWAY │        │SUPABASE │        │  CLAUDE │
│(Browser)│        │(Next.js)│        │(FastAPI)│        │  (DB)   │        │  (LLM)  │
└────┬────┘        └────┬────┘        └────┬────┘        └────┬────┘        └────┬────┘
     │                  │                  │                  │                  │
     │ 1. Type message  │                  │                  │                  │
     │    "Create RSI   │                  │                  │                  │
     │     strategy"    │                  │                  │                  │
     │─────────────────▶│                  │                  │                  │
     │                  │                  │                  │                  │
     │                  │ 2. Get JWT from  │                  │                  │
     │                  │    Supabase      │                  │                  │
     │                  │    session       │                  │                  │
     │                  │                  │                  │                  │
     │                  │ 3. POST /api/chat│                  │                  │
     │                  │    + Bearer JWT  │                  │                  │
     │                  │─────────────────▶│                  │                  │
     │                  │                  │                  │                  │
     │                  │                  │ 4. Validate JWT  │                  │
     │                  │                  │    Extract       │                  │
     │                  │                  │    user_id       │                  │
     │                  │                  │                  │                  │
     │                  │                  │ 5. Send to LLM   │                  │
     │                  │                  │─────────────────────────────────────▶│
     │                  │                  │                  │                  │
     │                  │                  │                  │                  │ 6. LLM decides
     │                  │                  │                  │                  │    to call tool:
     │                  │                  │                  │                  │    create_strategy
     │                  │                  │ 7. Tool call     │                  │
     │                  │                  │◀─────────────────────────────────────│
     │                  │                  │                  │                  │
     │                  │                  │ 8. Execute tool: │                  │
     │                  │                  │    Create        │                  │
     │                  │                  │    strategy JSON │                  │
     │                  │                  │                  │                  │
     │                  │                  │ 9. Run backtest  │                  │
     │                  │                  │    (in-memory    │                  │
     │                  │                  │     DuckDB)      │                  │
     │                  │                  │                  │                  │
     │                  │                  │ 10. Tool result  │                  │
     │                  │                  │─────────────────────────────────────▶│
     │                  │                  │                  │                  │
     │                  │                  │                  │                  │ 11. LLM formats
     │                  │                  │                  │                  │     response with
     │                  │                  │                  │                  │     results
     │                  │                  │ 12. Final response                  │
     │                  │                  │◀─────────────────────────────────────│
     │                  │                  │                  │                  │
     │                  │ 13. SSE stream   │                  │                  │
     │                  │◀─────────────────│                  │                  │
     │                  │                  │                  │                  │
     │ 14. Display      │                  │                  │                  │
     │     streaming    │                  │                  │                  │
     │     response     │                  │                  │                  │
     │◀─────────────────│                  │                  │                  │
     │                  │                  │                  │                  │
```

---

## Strategy Save/Load Flow (User Isolation)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    SAVE STRATEGY (User-Isolated)                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────┐        ┌─────────┐        ┌─────────┐        ┌─────────────────────────────────┐
│  USER   │        │ VERCEL  │        │ RAILWAY │        │            SUPABASE             │
│(Browser)│        │(Next.js)│        │(FastAPI)│        │                                 │
└────┬────┘        └────┬────┘        └────┬────┘        │  ┌──────────┐  ┌─────────────┐ │
     │                  │                  │             │  │   Auth   │  │  PostgreSQL │ │
     │                  │                  │             │  └────┬─────┘  └──────┬──────┘ │
     │                  │                  │             └───────┼───────────────┼────────┘
     │                  │                  │                     │               │
     │ 1. Click "Save"  │                  │                     │               │
     │─────────────────▶│                  │                     │               │
     │                  │                  │                     │               │
     │                  │ 2. POST          │                     │               │
     │                  │    /api/strategies                     │               │
     │                  │    + Bearer JWT  │                     │               │
     │                  │─────────────────▶│                     │               │
     │                  │                  │                     │               │
     │                  │                  │ 3. Validate JWT ───▶│               │
     │                  │                  │    user_id = abc123 │               │
     │                  │                  │◀────────────────────│               │
     │                  │                  │                     │               │
     │                  │                  │ 4. INSERT strategy  │               │
     │                  │                  │    with user_id     │               │
     │                  │                  │────────────────────────────────────▶│
     │                  │                  │                     │               │
     │                  │                  │                     │   ┌─────────────────────┐
     │                  │                  │                     │   │ strategies table    │
     │                  │                  │                     │   │                     │
     │                  │                  │                     │   │ id: uuid-1          │
     │                  │                  │                     │   │ user_id: abc123 ◀───┼─── RLS: only
     │                  │                  │                     │   │ name: "RSI_strat"   │    this user
     │                  │                  │                     │   │ config: {...}       │    can see
     │                  │                  │                     │   └─────────────────────┘
     │                  │                  │                     │               │
     │                  │                  │ 5. Success          │               │
     │                  │                  │◀────────────────────────────────────│
     │                  │                  │                     │               │
     │                  │ 6. Response      │                     │               │
     │                  │◀─────────────────│                     │               │
     │                  │                  │                     │               │
     │ 7. "Saved!"      │                  │                     │               │
     │◀─────────────────│                  │                     │               │


┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    LIST STRATEGIES (User-Isolated)                                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

     USER A (user_id: abc123)                    USER B (user_id: xyz789)
              │                                           │
              │                                           │
              ▼                                           ▼
    ┌─────────────────────┐                    ┌─────────────────────┐
    │ GET /api/strategies │                    │ GET /api/strategies │
    │ JWT: user abc123    │                    │ JWT: user xyz789    │
    └──────────┬──────────┘                    └──────────┬──────────┘
               │                                          │
               │                                          │
               ▼                                          ▼
    ┌──────────────────────────────────────────────────────────────────┐
    │                         SUPABASE PostgreSQL                       │
    │                                                                   │
    │  ┌─────────────────────────────────────────────────────────────┐ │
    │  │                     strategies table                         │ │
    │  │                                                              │ │
    │  │  id: uuid-1  │ user_id: abc123 │ name: "RSI_momentum"      │ │
    │  │  id: uuid-2  │ user_id: abc123 │ name: "EMA_cross"          │ │
    │  │  id: uuid-3  │ user_id: xyz789 │ name: "MACD_trend"         │ │
    │  │  id: uuid-4  │ user_id: xyz789 │ name: "Bollinger_bounce"   │ │
    │  │                                                              │ │
    │  └─────────────────────────────────────────────────────────────┘ │
    │                                                                   │
    │  ROW LEVEL SECURITY POLICY:                                      │
    │  SELECT * FROM strategies WHERE auth.uid() = user_id             │
    │                                                                   │
    └──────────────────────────────────────────────────────────────────┘
               │                                          │
               │                                          │
               ▼                                          ▼
    ┌─────────────────────┐                    ┌─────────────────────┐
    │ User A sees:        │                    │ User B sees:        │
    │ • RSI_momentum      │                    │ • MACD_trend        │
    │ • EMA_cross         │                    │ • Bollinger_bounce  │
    │                     │                    │                     │
    │ (NOT User B's)      │                    │ (NOT User A's)      │
    └─────────────────────┘                    └─────────────────────┘
```

---

## Complete Request Flow (All Components)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     COMPLETE USER JOURNEY                                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘


                                    ┌─────────────────────┐
                                    │        USER         │
                                    │      (Browser)      │
                                    └──────────┬──────────┘
                                               │
                              ┌────────────────┼────────────────┐
                              │                │                │
                              ▼                ▼                ▼
                    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
                    │   SIGNUP    │   │    LOGIN    │   │  USE APP    │
                    └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
                           │                 │                 │
                           ▼                 ▼                 │
                    ┌─────────────────────────────┐            │
                    │         SUPABASE AUTH       │            │
                    │  • Create/validate user     │            │
                    │  • Issue JWT token          │            │
                    │  • Manage session           │            │
                    └──────────────┬──────────────┘            │
                                   │                           │
                                   │  JWT Token                │
                                   ▼                           │
                    ┌─────────────────────────────┐            │
                    │         NEXT.JS APP         │◀───────────┘
                    │  • Store session            │
                    │  • Attach JWT to requests   │
                    │  • Render UI                │
                    └──────────────┬──────────────┘
                                   │
                                   │  API Request + JWT
                                   ▼
                    ┌─────────────────────────────┐
                    │       FASTAPI SERVER        │
                    │  1. Validate JWT            │
                    │  2. Extract user_id         │
                    │  3. Process request         │
                    └──────────────┬──────────────┘
                                   │
             ┌─────────────────────┼─────────────────────┐
             │                     │                     │
             ▼                     ▼                     ▼
    ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
    │   CHAT/LLM      │   │    BACKTEST     │   │  DATA INGEST    │
    │                 │   │                 │   │                 │
    │ • Send to Claude│   │ • Load user's   │   │ • Fetch from    │
    │ • Tool calling  │   │   market data   │   │   Yahoo Finance │
    │ • Stream resp.  │   │   (Supabase)    │   │ • Store with    │
    │                 │   │ • Run engine    │   │   user_id       │
    │                 │   │ • Return metrics│   │                 │
    └────────┬────────┘   └────────┬────────┘   └────────┬────────┘
             │                     │                     │
             ▼                     │                     │
    ┌─────────────────┐            │                     │
    │   ANTHROPIC     │            │                     │
    │   CLAUDE API    │            │                     │
    └─────────────────┘            │                     │
                                   │                     │
                                   └──────────┬──────────┘
                                              │
                                              ▼
                                   ┌─────────────────────┐
                                   │      SUPABASE       │
                                   │     POSTGRESQL      │
                                   │                     │
                                   │  • market_data      │
                                   │  • strategies       │
                                   │  • conversations    │
                                   │                     │
                                   │  ALL with RLS       │
                                   │  (user isolation)   │
                                   └─────────────────────┘
```

---

## Data Flow Summary

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                        DATA OWNERSHIP                                                 │
│                              ALL USER DATA IS ISOLATED (No Shared Data)                              │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     USER-SPECIFIC DATA                                               │
│                                   (ALL isolated per user_id)                                         │
│                                                                                                      │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐                       │
│  │      strategies      │  │    conversations     │  │       usage          │                       │
│  │                      │  │                      │  │                      │                       │
│  │  • Strategy configs  │  │  • Chat history      │  │  • Backtest count    │                       │
│  │  • Backtest results  │  │  • Message logs      │  │  • Conversation ct   │                       │
│  │  • Tags, metadata    │  │                      │  │  • Feature usage     │                       │
│  │                      │  │                      │  │                      │                       │
│  │  RLS: user_id match  │  │  RLS: user_id match  │  │  RLS: user_id match  │                       │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘                       │
│                                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                                    market_data (OHLCV)                                        │   │
│  │                                                                                               │   │
│  │  • Each user ingests their own symbols                                                        │   │
│  │  • User A has AAPL, SPY → only User A sees it                                                │   │
│  │  • User B has TSLA, QQQ → only User B sees it                                                │   │
│  │  • If both want SPY, each has their own copy (storage is cheap)                              │   │
│  │                                                                                               │   │
│  │  RLS: user_id match                                                                           │   │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                                      │
│                                    ALL stored in: SUPABASE PostgreSQL                                │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Market Data Isolation

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    USER-SPECIFIC MARKET DATA                                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

     USER A (user_id: abc123)                    USER B (user_id: xyz789)
              │                                           │
              │ "Ingest AAPL and SPY"                     │ "Ingest TSLA and SPY"
              ▼                                           ▼
    ┌─────────────────────┐                    ┌─────────────────────┐
    │ POST /api/data/     │                    │ POST /api/data/     │
    │      ingest         │                    │      ingest         │
    │ JWT: user abc123    │                    │ JWT: user xyz789    │
    │ symbol: AAPL        │                    │ symbol: TSLA        │
    └──────────┬──────────┘                    └──────────┬──────────┘
               │                                          │
               ▼                                          ▼
    ┌──────────────────────────────────────────────────────────────────┐
    │                     FASTAPI: Data Ingestion                       │
    │                                                                   │
    │  1. Validate JWT → extract user_id                               │
    │  2. Fetch data from Yahoo Finance                                │
    │  3. Store in Supabase with user_id                               │
    └──────────────────────────────────────────────────────────────────┘
               │                                          │
               ▼                                          ▼
    ┌──────────────────────────────────────────────────────────────────┐
    │                         SUPABASE PostgreSQL                       │
    │                                                                   │
    │  ┌─────────────────────────────────────────────────────────────┐ │
    │  │                     market_data table                        │ │
    │  │                                                              │ │
    │  │  user_id   │ symbol │ timeframe │ timestamp  │ OHLCV...     │ │
    │  │  ──────────┼────────┼───────────┼────────────┼──────────    │ │
    │  │  abc123    │ AAPL   │ 1d        │ 2024-01-02 │ ...          │ │
    │  │  abc123    │ AAPL   │ 1d        │ 2024-01-03 │ ...          │ │
    │  │  abc123    │ SPY    │ 1d        │ 2024-01-02 │ ...          │ │
    │  │  xyz789    │ TSLA   │ 1d        │ 2024-01-02 │ ...          │ │
    │  │  xyz789    │ SPY    │ 1d        │ 2024-01-02 │ ...    ◀─────┼─── Same symbol,
    │  │                                                              │    different user
    │  └─────────────────────────────────────────────────────────────┘ │
    │                                                                   │
    │  ROW LEVEL SECURITY:                                             │
    │  SELECT/INSERT/UPDATE/DELETE WHERE auth.uid() = user_id          │
    │                                                                   │
    └──────────────────────────────────────────────────────────────────┘
               │                                          │
               │                                          │
               ▼                                          ▼
    ┌─────────────────────┐                    ┌─────────────────────┐
    │ User A sees:        │                    │ User B sees:        │
    │ • AAPL              │                    │ • TSLA              │
    │ • SPY               │                    │ • SPY               │
    │                     │                    │                     │
    │ (NOT TSLA)          │                    │ (NOT AAPL)          │
    └─────────────────────┘                    └─────────────────────┘


┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                      BACKTEST WITH USER DATA                                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

     USER A wants to backtest on AAPL
              │
              ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                        FASTAPI: Run Backtest                     │
    │                                                                  │
    │  1. JWT validated → user_id = abc123                            │
    │                                                                  │
    │  2. Query market_data WHERE user_id = abc123 AND symbol = AAPL  │
    │     (RLS automatically enforces this)                           │
    │                                                                  │
    │  3. Run backtest engine on that data                            │
    │                                                                  │
    │  4. Return results                                               │
    └─────────────────────────────────────────────────────────────────┘

     If User A tries to backtest TSLA (which they haven't ingested):
     → "No data found for TSLA. Please ingest data first."

     If User B tries to access User A's AAPL data:
     → RLS blocks it, returns empty result
```

---

## Security Boundaries

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                      SECURITY MODEL                                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

                           TRUST BOUNDARY
                                 │
    UNTRUSTED                    │                    TRUSTED
    (Public Internet)            │                    (Backend Systems)
                                 │
    ┌─────────────┐              │              ┌─────────────────────────┐
    │             │              │              │                         │
    │   Browser   │─────────────▶│─────────────▶│      Vercel Edge        │
    │             │   HTTPS      │              │    (serves frontend)    │
    │             │   only       │              │                         │
    └─────────────┘              │              └────────────┬────────────┘
                                 │                           │
                                 │              ┌────────────▼────────────┐
                                 │              │                         │
                                 │              │    Railway API          │
                                 │◀─────────────│    • JWT validation     │
                                 │   Must have  │    • User extraction    │
                                 │   valid JWT  │    • Authorization      │
                                 │              │                         │
                                 │              └────────────┬────────────┘
                                 │                           │
                                 │              ┌────────────▼────────────┐
                                 │              │                         │
                                 │              │    Supabase             │
                                 │◀─────────────│    • RLS enforcement    │
                                 │   JWT signed │    • Data isolation     │
                                 │   by Supabase│                         │
                                 │              └─────────────────────────┘
                                 │

    WHAT EACH LAYER ENFORCES:
    ─────────────────────────────────────────────────────────────────────
    Vercel Middleware:    Session exists → allow access to app pages
    Railway API:          Valid JWT → extract user_id for all operations
    Supabase RLS:         user_id match → only return user's own rows
    ─────────────────────────────────────────────────────────────────────

    ATTACK PREVENTION:
    ─────────────────────────────────────────────────────────────────────
    No JWT:               → 401 Unauthorized
    Expired JWT:          → 401 Unauthorized
    Forged JWT:           → 401 (signature validation fails)
    Valid JWT, wrong user:→ RLS returns empty (can't see other's data)
    SQL Injection:        → Parameterized queries + ORM
    XSS:                  → React auto-escapes, CSP headers
    ─────────────────────────────────────────────────────────────────────
```

---

*These diagrams represent the target architecture for launch. All user data is isolated via Row Level Security in Supabase PostgreSQL.*
