# Launch Plan: From Code to Users

**Goal:** Ship high-priority features, deploy to production, and get first 100 users.

**Timeline:** 2-3 weeks
**Budget:** ~$100-200/mo for infrastructure

---

## Phase 1: Feature Sprint (Week 1)

### Priority Order

| Day | Feature | Effort | Why First |
|-----|---------|--------|-----------|
| 1-2 | F019: pandas-ta | 1.5 days | "130+ indicators" is a marketing hook |
| 2 | F021: Trailing stops | 0.5 day | Quick win, enables "let winners run" |
| 3-4 | F020: Short selling | 1.5 days | "Long AND short" doubles appeal |
| 4-5 | **Supabase Auth** | 1.5 days | User accounts, data isolation |
| 5 | Polish & bug fixes | 0.5 day | Don't ship broken |

**Skip for launch:** F022 (rolling lookback), F002 (plugins) — nice to have, not essential for v1

### Definition of Done
- [ ] User can select VWAP, ADX, Donchian in strategy
- [ ] User can create short strategies
- [ ] Trailing stops work
- [ ] **User can sign up / sign in (email + Google)**
- [ ] **Each user only sees their own strategies**
- [ ] No crashes on happy path
- [ ] Mobile-responsive (people will check on phones)

---

## Phase 1.5: Supabase Authentication (HIGH PRIORITY)

### What Supabase Provides

| Feature | What It Does | Cost |
|---------|--------------|------|
| **Auth** | Email/password, Google, GitHub OAuth | Free |
| **PostgreSQL** | Database for strategies, user data | Free (500MB) |
| **Row Level Security** | Each user only sees their data | Built-in |
| **Edge Functions** | Serverless functions (optional) | Free tier |
| **Realtime** | Live updates (optional) | Free tier |

**Free tier limits:** 50,000 monthly active users, 500MB database, 1GB file storage

### Architecture with Supabase

```
┌─────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (Vercel)                          │
│  Next.js + @supabase/supabase-js + @supabase/auth-helpers-nextjs    │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
        ┌───────────────────┐   ┌───────────────────────────┐
        │     Supabase      │   │      Railway (API)        │
        │  ┌─────────────┐  │   │                           │
        │  │    Auth     │  │   │  FastAPI + DuckDB         │
        │  │  (sessions) │  │   │  (backtesting engine)     │
        │  └─────────────┘  │   │                           │
        │  ┌─────────────┐  │   │  Validates Supabase JWT   │
        │  │  PostgreSQL │  │   │                           │
        │  │ (strategies)│  │   └───────────────────────────┘
        │  └─────────────┘  │
        └───────────────────┘
```

### Database Schema (Supabase PostgreSQL)

```sql
-- Users table (auto-created by Supabase Auth)
-- auth.users

-- ============================================================
-- MARKET DATA (User-specific - each user ingests their own data)
-- ============================================================
CREATE TABLE market_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,  -- '1m', '5m', '15m', '1h', '4h', '1d'
    timestamp TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Each user can only have one bar per symbol/timeframe/timestamp
    UNIQUE(user_id, symbol, timeframe, timestamp)
);

-- Index for fast queries
CREATE INDEX idx_market_data_user_symbol ON market_data(user_id, symbol, timeframe, timestamp);

-- RLS: Users only see their own market data
ALTER TABLE market_data ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own market data"
    ON market_data FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own market data"
    ON market_data FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own market data"
    ON market_data FOR DELETE
    USING (auth.uid() = user_id);

-- ============================================================
-- STRATEGIES (User-specific)
-- ============================================================
CREATE TABLE strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    config JSONB NOT NULL,
    version INT DEFAULT 1,
    tags TEXT[] DEFAULT '{}',
    last_backtest JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(user_id, name)
);

ALTER TABLE strategies ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own strategies"
    ON strategies FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own strategies"
    ON strategies FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own strategies"
    ON strategies FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own strategies"
    ON strategies FOR DELETE
    USING (auth.uid() = user_id);

-- ============================================================
-- CONVERSATIONS (User-specific chat history)
-- ============================================================
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT,
    messages JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own conversations"
    ON conversations FOR ALL
    USING (auth.uid() = user_id);

-- ============================================================
-- HELPER VIEW: User's available symbols
-- ============================================================
CREATE VIEW user_symbols AS
SELECT DISTINCT
    user_id,
    symbol,
    timeframe,
    MIN(timestamp) as first_date,
    MAX(timestamp) as last_date,
    COUNT(*) as bar_count
FROM market_data
GROUP BY user_id, symbol, timeframe;
```

### Frontend Implementation (Next.js)

**1. Install packages:**
```bash
cd web
npm install @supabase/supabase-js @supabase/auth-helpers-nextjs
```

**2. Environment variables:**
```bash
# .env.local
NEXT_PUBLIC_SUPABASE_URL=https://xxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIs...
```

**3. Create Supabase client:**
```typescript
// lib/supabase.ts
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'

export const supabase = createClientComponentClient()
```

**4. Auth UI component:**
```typescript
// components/Auth.tsx
import { Auth } from '@supabase/auth-ui-react'
import { ThemeSupa } from '@supabase/auth-ui-shared'
import { supabase } from '@/lib/supabase'

export function AuthForm() {
  return (
    <Auth
      supabaseClient={supabase}
      appearance={{ theme: ThemeSupa }}
      providers={['google']}
      redirectTo={`${window.location.origin}/auth/callback`}
    />
  )
}
```

**5. Protect routes:**
```typescript
// middleware.ts
import { createMiddlewareClient } from '@supabase/auth-helpers-nextjs'
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export async function middleware(req: NextRequest) {
  const res = NextResponse.next()
  const supabase = createMiddlewareClient({ req, res })
  const { data: { session } } = await supabase.auth.getSession()

  // Redirect to login if not authenticated
  if (!session && req.nextUrl.pathname !== '/login') {
    return NextResponse.redirect(new URL('/login', req.url))
  }

  return res
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|login|auth).*)']
}
```

### Backend: Validate Supabase JWT (FastAPI)

```python
# api/auth.py
from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

async def get_current_user(request: Request) -> str:
    """Extract and validate user ID from Supabase JWT."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")

    token = auth_header.split(" ")[1]

    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated"
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Use in routes
@app.get("/api/strategies")
async def list_strategies(user_id: str = Depends(get_current_user)):
    # user_id is guaranteed to be the authenticated user
    strategies = await get_user_strategies(user_id)
    return strategies
```

### Supabase Setup Checklist

```
[ ] Create Supabase project (supabase.com)
[ ] Get project URL and anon key
[ ] Enable Google OAuth provider (optional but nice)
    - Create Google Cloud OAuth credentials
    - Add to Supabase Auth settings
[ ] Run SQL schema (strategies table + RLS policies)
[ ] Add environment variables to:
    - Vercel (frontend)
    - Railway (backend)
[ ] Install npm packages in web/
[ ] Create auth components
[ ] Add middleware for protected routes
[ ] Update API routes to validate JWT
[ ] Test: signup → create strategy → logout → login → see strategy
```

### User Experience Flow

```
1. User visits site
   ↓
2. Sees landing page with [Sign Up] [Log In]
   ↓
3. Clicks Sign Up → Supabase Auth UI
   - Email/password OR
   - "Continue with Google" (one click)
   ↓
4. Redirected to app, session stored
   ↓
5. Creates strategies (saved to their account)
   ↓
6. Can log out, log back in, see their strategies
   ↓
7. Different device? Log in, same strategies
```

### What Users See

**Not logged in:**
- Landing page
- Login/signup forms
- Demo video
- "Try free" CTA

**Logged in:**
- Chat interface
- Their saved strategies
- Their backtest history
- Account settings (change password, delete account)

---

## Phase 2: Deployment (Day 6-7)

### Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Vercel        │     │   Railway       │
│   (Frontend)    │────▶│   (API)         │
│   Next.js       │     │   FastAPI       │
│   $0/mo free    │     │   $5-20/mo      │
└─────────────────┘     └────────┬────────┘
                                 │
                                 │
                                 ▼
                        ┌─────────────────┐
                        │    Supabase     │
                        │                 │
                        │  • Auth         │
                        │  • PostgreSQL   │
                        │    - market_data│
                        │    - strategies │
                        │    - convos     │
                        │  • RLS (isolate)│
                        │                 │
                        │  $0/mo free     │
                        └─────────────────┘
```

**Note:** All user data (market data, strategies, conversations) is stored in Supabase PostgreSQL with Row Level Security. Each user only sees their own data.

### Services & Costs

| Service | Purpose | Cost | Notes |
|---------|---------|------|-------|
| **Vercel** | Frontend hosting | $0 | Free tier, 100GB bandwidth |
| **Railway** | API + DuckDB | $5-20/mo | Pay for usage |
| **Supabase** | Auth + DB | $0 | Free tier: 50K MAU, 500MB |
| **Cloudflare** | Domain + CDN | $0 | Free tier |
| **Anthropic** | Claude API | ~$20-50/mo | ~$0.10-0.30 per conversation |
| **Sentry** | Error tracking | $0 | Free tier |
| **PostHog** | Analytics | $0 | Free tier: 1M events |

**Total: ~$25-70/mo to start**

### Domain Options

| Domain | Availability | Cost |
|--------|--------------|------|
| bonito.ai | Probably taken | Check |
| getbonito.com | Maybe | ~$12/yr |
| usebonito.com | Likely available | ~$12/yr |
| trybonito.com | Likely available | ~$12/yr |
| bonito.trade | Maybe | ~$30/yr |
| bonito.dev | Likely available | ~$12/yr |

**Recommendation:** Check bonito.ai first, fallback to trybonito.com

### Deployment Checklist

```
Day 5-6 (Supabase + Deploy):
[ ] Create Supabase project
[ ] Run database schema (strategies table + RLS)
[ ] Enable Google OAuth in Supabase
[ ] Buy domain
[ ] Set up Vercel project, connect GitHub
[ ] Set up Railway project
[ ] Configure environment variables (both services)
[ ] Deploy API to Railway
[ ] Deploy frontend to Vercel
[ ] Test end-to-end auth flow

Day 7 (Polish):
[ ] Configure Cloudflare DNS
[ ] Set up Sentry error tracking
[ ] Set up PostHog analytics
[ ] Add basic rate limiting
[ ] Test on mobile
[ ] SSL working (automatic with Vercel)
[ ] Test: signup → strategy → logout → login → see strategy
```

### Environment Variables Needed

```bash
# API (Railway)
ANTHROPIC_API_KEY=sk-...
DATABASE_URL=duckdb:///data/market_data.duckdb
CORS_ORIGINS=https://yourdomain.com

# Frontend (Vercel)
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

---

## Phase 3: Pre-Launch Prep (Day 8-9)

### Landing Page Content

**Hero:**
> **From idea to backtested strategy in 60 seconds.**
> Describe your trading strategy in plain English. Our AI builds it, tests it, and helps you improve it.
> [Try Free] [Watch Demo]

**Features to highlight:**
- 🧠 Natural language → working strategy
- ⚡ Sub-second backtesting
- 📊 130+ technical indicators
- 📈 Long AND short strategies
- 🛡️ Trailing stops built-in
- 💾 Save and iterate

**Social proof (for later):**
- "X strategies created"
- "X backtests run"
- User testimonials

### Demo Video (2-3 minutes)

Script:
```
0:00 - "What if you could test a trading idea in 60 seconds?"
0:15 - Type: "Create an RSI momentum strategy for SPY"
0:30 - Show agent creating strategy
0:45 - Show backtest results
1:00 - "Now let's improve it"
1:15 - Type: "Add a trend filter and trailing stop"
1:30 - Show improved results
1:45 - "130+ indicators, long and short, no coding required"
2:00 - "Try it free at [domain]"
```

**Tools:** Loom (free), or Screen Studio ($89 one-time) for polish

### Assets Needed

- [ ] Logo (use Midjourney or just clean text for now)
- [ ] OG image for social sharing (1200x630px)
- [ ] Demo video
- [ ] Screenshot of the UI
- [ ] Favicon

---

## Phase 4: Soft Launch (Day 10-11)

### Goal: 20-50 users from warm channels

### Where to Post

**1. Reddit**

| Subreddit | Members | Rules | Approach |
|-----------|---------|-------|----------|
| r/algotrading | 230K | Self-promo Saturday only | Wait for Saturday, or comment helpfully first |
| r/learnprogramming | 4M | Show what you built | "I built an AI trading strategy builder" |
| r/SideProject | 200K | Show your work | Perfect for this |
| r/artificial | 1M | AI projects welcome | Focus on the AI angle |
| r/Python | 1.2M | Project showcase | If you post the code angle |
| r/Daytrading | 1.5M | Careful, skeptical | Don't oversell |

**Reddit Post Template:**
```
Title: I built an AI that creates trading strategies from plain English

Hey r/[subreddit],

I spent the last few weeks building something I wish existed:
You describe a trading strategy in plain English, and an AI:
1. Creates the strategy config
2. Backtests it instantly
3. Helps you iterate and improve

Example: "Create an RSI momentum strategy with a trend filter"
→ Full backtest results in seconds

Features:
- 130+ indicators (pandas-ta)
- Long and short strategies
- Trailing stops
- Save and load strategies

It's free to try: [link]

Would love feedback from actual traders. What would make this useful for you?

[Demo video/gif]
```

**2. Twitter/X**

```
Thread idea:

1/ I built an AI that turns plain English into backtested trading strategies.

No code. No Pine Script. Just describe what you want.

Here's how it works 🧵

2/ The problem: Testing a trading idea takes hours.
- Learn Pine Script or Python
- Figure out the backtesting library
- Debug indicator calculations
- Finally see if it even works

3/ The solution: Just say what you want.

"Create an RSI momentum strategy with a 100-day SMA filter and trailing stop"

30 seconds later: Full backtest results.

4/ [Video/GIF of it working]

5/ How it works:
- AI parses your intent
- Generates a strategy config
- Runs vectorized backtest
- Explains the results
- Suggests improvements

6/ Features:
- 130+ indicators
- Long and short
- Trailing stops
- Sub-second backtests

7/ Try it free: [link]

Built this because I was tired of spending hours testing simple ideas.

What strategies would you test first?
```

**3. Discord Communities**

| Server | How to Join | Approach |
|--------|-------------|----------|
| Algo Trading Discord | Google it | Share in #showcase |
| Python Discord | python.org | #show-off channel |
| Indie Hackers Discord | indiehackers.com | Share your build |
| r/algotrading Discord | In subreddit sidebar | #projects channel |

**4. Hacker News**

- Post as "Show HN: AI-powered trading strategy builder"
- Best time: Tuesday-Thursday, 8-10am EST
- Be ready to answer questions
- Don't oversell — HN hates hype

**5. Product Hunt**

- Save for later (after you have more polish)
- Need to line up supporters
- Hunter helps (find someone with followers)

---

## Phase 5: Feedback Loop (Week 2-3)

### Track Everything

**PostHog events to track:**
```javascript
// Key events
posthog.capture('strategy_created', { indicators: [...] })
posthog.capture('backtest_run', { symbol, timeframe })
posthog.capture('strategy_saved')
posthog.capture('chat_message_sent')
posthog.capture('signup')  // if you add auth
```

**Questions to answer:**
- Where do users drop off?
- What strategies do they try to create?
- What errors do they hit?
- How many come back Day 2?

### Collect Feedback

**Add to UI:**
```
[Feedback?] button → Opens form/email

"What would make this more useful?"
"What's confusing?"
"Would you pay for this? How much?"
```

**Or simple:**
- Email link: feedback@yourdomain.com
- Twitter DMs open
- Discord server (once you have 50+ users)

### What to Do With Feedback

| Feedback Type | Action |
|---------------|--------|
| Bug report | Fix immediately |
| Feature request | Log it, prioritize later |
| "I'd pay for X" | Build X |
| Confusion about UI | Improve onboarding |
| Silence | Worry, reach out manually |

---

## Phase 6: Growth (Week 3+)

### Content Marketing (Free, Slow, Compounds)

**Blog posts:**
- "How I Built an AI Trading Strategy Builder"
- "Backtesting RSI Strategies: What Actually Works"
- "EMA Crossover Strategies: A Complete Guide"
- "Why Most Trading Strategies Fail (And How to Fix Them)"

**SEO targets:**
- "ai trading strategy builder"
- "backtest trading strategy free"
- "rsi strategy backtest"
- "algo trading for beginners"

**YouTube:**
- Screen recordings of building strategies
- "I tested 100 RSI strategies with AI"
- Strategy breakdowns

### Community Building

**Discord server** (once you have 50+ users):
- #general
- #strategies (share what you've built)
- #feedback
- #bugs

**Newsletter:**
- Weekly "Strategy of the Week"
- Platform updates
- Trading insights

### Paid (Later, Once PMF Confirmed)

| Channel | Cost | Expected |
|---------|------|----------|
| Google Ads ("backtest trading strategy") | $2-5/click | Test with $100 |
| Twitter/X ads | $1-3/click | Retarget visitors |
| Reddit ads (r/algotrading) | $1-2/click | Very targeted |
| Influencer sponsorship | $100-500 | Trading YouTubers |

**Don't spend money until you have 100+ organic users and know the product works.**

---

## Budget Summary

### Launch Month

| Item | Cost |
|------|------|
| Domain | $12-30 |
| Railway (API hosting) | $5-20 |
| Vercel (Frontend) | $0 |
| Supabase (Auth/DB) | $0 |
| Anthropic API | $20-50 |
| Sentry | $0 |
| PostHog | $0 |
| Screen Studio (optional) | $89 one-time |
| **Total** | **$40-100** |

### Monthly Ongoing

| Users | Anthropic | Railway | Total |
|-------|-----------|---------|-------|
| 50 | $20-30 | $10 | ~$40 |
| 200 | $50-80 | $20 | ~$80 |
| 500 | $100-150 | $30 | ~$150 |
| 1,000 | $200-300 | $50 | ~$300 |

**You can get to 1,000 users for ~$300/mo in infrastructure.**

---

## Success Metrics

### Week 1 (Feature Sprint)
- [ ] pandas-ta integrated
- [ ] Short selling works
- [ ] Trailing stops work
- [ ] Deployed to production

### Week 2 (Soft Launch)
- [ ] 50 users signed up
- [ ] 20 backtests run by non-you
- [ ] 5 pieces of feedback collected
- [ ] Zero critical bugs

### Week 3 (Iterate)
- [ ] 100 users
- [ ] Top feedback item addressed
- [ ] Second round of posting
- [ ] 3 users say "I'd pay for this"

### Month 1
- [ ] 200+ users
- [ ] Clear understanding of what people want
- [ ] Decision: keep building or pivot

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Nobody cares | Post in multiple channels, iterate messaging |
| Too many bugs | Soft launch to small group first |
| LLM costs explode | Add rate limiting, optimize prompts |
| Negative feedback | It's data, not defeat — learn from it |
| Competitor launches | Move faster, you're already ahead |

---

## Quick Reference: Launch Checklist

```
WEEK 1: BUILD
[ ] pandas-ta integration (Day 1-2)
[ ] Trailing stops (Day 2)
[ ] Short selling (Day 3-4)
[ ] Supabase auth setup (Day 4-5)
    [ ] Create project
    [ ] Database schema + RLS
    [ ] Google OAuth
    [ ] Frontend auth components
    [ ] Backend JWT validation
[ ] Deploy to Railway + Vercel (Day 5-6)
[ ] Domain + SSL (Day 6)
[ ] Test full auth flow (Day 7)
[ ] Basic analytics (PostHog)

WEEK 2: LAUNCH
[ ] Record demo video
[ ] Write Reddit post
[ ] Write Twitter thread
[ ] Post to r/SideProject
[ ] Post to r/algotrading (Saturday)
[ ] Share in Discord communities
[ ] Hacker News (Show HN)

WEEK 3: ITERATE
[ ] Fix top 3 bugs
[ ] Build most-requested feature
[ ] Second round of posting
[ ] Start collecting testimonials
[ ] Plan paid tier (Stripe + Supabase)
```

---

## What "Success" Looks Like

**After 30 days:**

| Outcome | What It Means |
|---------|---------------|
| 0 users | Messaging problem or wrong channels |
| 10-50 users, no engagement | Product doesn't solve real problem |
| 50-100 users, good engagement | You have something, keep going |
| 100+ users, "I'd pay" comments | PMF signals, start thinking about pricing |
| 500+ users | Time to quit your job |

---

*Stop planning. Start shipping. The market will tell you what to build.*
