# Pricing Strategy

**Status:** Planning (implement after initial launch)
**Last Updated:** December 2025

> **Launch Strategy:** Ship with free tier only. Add paid tiers after 50-100 users and feedback.

---

## Cost Structure

### Variable Costs (Per User)

| Cost | Per Unit | Notes |
|------|----------|-------|
| Claude API | ~$0.10-0.30/conversation | Main cost driver |
| Backtest compute | ~$0.001/backtest | Negligible |
| Database storage | ~$0.01/user/month | Negligible |

### Fixed Costs (Monthly)

| Service | Cost | Notes |
|---------|------|-------|
| Railway (API) | $5-50 | Scales with usage |
| Supabase | $0-25 | Free → Pro at scale |
| Vercel | $0-20 | Free tier generous |
| Domain | ~$1 | Annual amortized |
| **Total** | **$10-100** | Before Claude costs |

### Cost Per Active User

| User Type | Claude Usage | Monthly Cost |
|-----------|--------------|--------------|
| Light (5 conversations) | $0.50-1.50 | ~$1 |
| Medium (20 conversations) | $2-6 | ~$4 |
| Heavy (50 conversations) | $5-15 | ~$10 |

---

## Pricing Tiers

### Recommended Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                           FREE                                   │
│                          $0/month                                │
├─────────────────────────────────────────────────────────────────┤
│  ✓ 3 saved strategies                                           │
│  ✓ 10 backtests/month                                           │
│  ✓ 15 AI conversations/month                                    │
│  ✓ Basic indicators (SMA, EMA, RSI, MACD, ATR, BBands, Stoch)  │
│  ✓ Daily timeframe only                                         │
│  ✗ Short selling                                                │
│  ✗ Trailing stops                                               │
│  ✗ Advanced indicators (VWAP, ADX, Donchian, etc.)             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                           PRO                                    │
│                    $29/month or $249/year                        │
├─────────────────────────────────────────────────────────────────┤
│  ✓ Unlimited saved strategies                                   │
│  ✓ Unlimited backtests                                          │
│  ✓ Unlimited AI conversations                                   │
│  ✓ All 130+ indicators                                          │
│  ✓ All timeframes (1m, 5m, 15m, 1h, 4h, 1d)                    │
│  ✓ Short selling                                                │
│  ✓ Trailing stops                                               │
│  ✓ Strategy export (JSON)                                       │
│  ✓ Email support (48hr response)                                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                          TEAM                                    │
│                    $79/month or $699/year                        │
├─────────────────────────────────────────────────────────────────┤
│  ✓ Everything in Pro                                            │
│  ✓ 5 team seats included                                        │
│  ✓ API access (REST)                                            │
│  ✓ Priority support (24hr response)                             │
│  ✓ Shared strategy library                                      │
│  ✓ Coming: Custom indicators                                    │
│  ✓ Coming: Webhook alerts                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Unit Economics

### Revenue Model

| Metric | Value |
|--------|-------|
| Target Free → Pro conversion | 5-10% |
| Target Pro → Team conversion | 10-20% |
| Target monthly churn (Pro) | <5% |
| Target annual plan adoption | 30-40% |

### At Scale (1000 users)

```
User Distribution:
├── 800 Free (80%)
├── 150 Pro (15%)
└── 50 Team (5%)

Monthly Revenue:
├── Free:  800 × $0   = $0
├── Pro:   150 × $29  = $4,350
├── Team:   50 × $79  = $3,950
└── Total MRR:        = $8,300

Monthly Costs:
├── Claude API:       ~$500
├── Infrastructure:   ~$200
└── Total:            ~$700

Gross Margin: ~92%
ARR: ~$100,000
```

### Break-Even

```
Fixed costs: ~$100/mo (minimum infrastructure)
Variable cost per active user: ~$3/mo average

Break-even: 5 Pro users or 2 Team users
```

---

## Implementation

### Phase 1: Launch (Free Only)

No payment processing. Everyone gets limited free tier.

```
Limits enforced:
- strategies: 3 max
- backtests: 10/month
- conversations: 15/month
- features: basic only
```

### Phase 2: Add Payments (After 50-100 users)

**Stripe Setup:**
1. Create Stripe account
2. Create products (Pro, Team)
3. Set up Customer Portal
4. Implement webhooks

**Database additions:**
```sql
-- Add to Supabase
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT UNIQUE,
    plan TEXT DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'team')),
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'canceled', 'past_due', 'trialing')),
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    period_start DATE DEFAULT date_trunc('month', NOW()),
    backtests INT DEFAULT 0,
    conversations INT DEFAULT 0,
    strategies_created INT DEFAULT 0,
    UNIQUE(user_id, period_start)
);

-- RLS
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own subscription"
    ON subscriptions FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can view own usage"
    ON usage FOR SELECT USING (auth.uid() = user_id);
```

**Stripe Webhook Events:**
```python
# Handle these events
'checkout.session.completed'  # New subscription
'customer.subscription.updated'  # Plan change
'customer.subscription.deleted'  # Cancellation
'invoice.payment_failed'  # Payment issue
```

### Phase 3: Optimize

- A/B test $29 vs $39
- Add annual plans
- Consider Team tier if demand
- Adjust limits based on actual usage

---

## Competitive Analysis

| Platform | Free Tier | Paid | Positioning |
|----------|-----------|------|-------------|
| TradingView | Limited charts | $15-60/mo | Charts + Pine Script |
| QuantConnect | 500 backtests | $8-50/mo | Coders |
| Composer | Very limited | $15-40/mo | No-code ETF |
| Alpaca | Free | Free | Broker (earns on trades) |
| **Bonito** | 10 backtests | $29/mo | AI + no-code |

**Our differentiation:** AI-powered iteration, natural language, no coding required.

---

## Pricing Psychology

### Why $29?

| Price Point | Perception |
|-------------|------------|
| $9 | "Too cheap, probably bad" |
| $19 | "Budget tool" |
| **$29** | "Professional, reasonable" |
| $49 | "Do I need this much?" |
| $99+ | "Enterprise" |

$29 is the prosumer sweet spot.

### Anchoring

Show Team ($79) first on pricing page → Pro ($29) feels cheap.

### Annual Discount

```
Pro: $29/mo → $249/yr (28% off, $20.75/mo)
Team: $79/mo → $699/yr (26% off, $58.25/mo)
```

Encourages commitment, reduces churn, improves cash flow.

---

## Upgrade Triggers

### In-App Prompts

| Trigger | Message |
|---------|---------|
| Hit 3 strategies | "You've saved 3 strategies. Upgrade to Pro for unlimited." |
| Hit 10 backtests | "You've used all 10 backtests this month. Upgrade for unlimited." |
| Try to use shorts | "Short selling is a Pro feature. Upgrade to unlock." |
| Try VWAP/ADX | "Advanced indicators require Pro. Upgrade to access 130+ indicators." |

### Email Sequences

```
Day 3: "How's your first strategy going?"
Day 7: "3 strategies that beat the market (Pro users only)"
Day 14: "Your free backtests reset. Here's what Pro users are building..."
Day 30: "Last chance: 20% off your first month of Pro"
```

---

## Billing Edge Cases

### Proration

- Upgrade mid-cycle: Charge prorated amount
- Downgrade mid-cycle: Credit applied to next invoice

### Failed Payments

1. First failure: Retry in 3 days, email user
2. Second failure: Retry in 3 days, warning email
3. Third failure: Downgrade to free, final email

### Cancellation

- Cancel at period end (keep access until then)
- No refunds for partial months
- Offer "pause subscription" as alternative

### Team Seats

- $79 includes 5 seats
- Additional seats: $15/seat/month
- Seat management in team admin panel

---

## Future Considerations

### Usage-Based Addon

```
If we add compute-heavy features:
- Walk-forward optimization: $0.10/run
- Multi-symbol portfolio: $0.05/symbol/backtest
- Options backtesting: $0.20/backtest
```

### Enterprise Tier

```
ENTERPRISE    Custom pricing
- Unlimited seats
- SSO/SAML
- Dedicated support
- Custom integrations
- SLA guarantee
- On-premise option
```

### Paper Trading Addon

```
When Alpaca integration ships:
- Free tier: View only
- Pro: Paper trading included
- Live trading: Separate terms (regulatory)
```

---

## Metrics to Track

### Conversion

- Free → Pro rate (target: 5-10%)
- Trial → Paid rate (if we add trials)
- Monthly vs Annual split

### Revenue

- MRR, ARR
- ARPU (Average Revenue Per User)
- LTV (Lifetime Value)

### Churn

- Monthly churn rate (target: <5%)
- Churn reasons (survey on cancel)
- Reactivation rate

### Usage

- Backtests per user
- Conversations per user
- Feature adoption (shorts, trailing stops)
- Limit hit rate (who's bumping into free limits)

---

## Launch Checklist (When Ready)

```
[ ] Stripe account verified
[ ] Products created (Pro monthly, Pro annual, Team monthly, Team annual)
[ ] Customer Portal configured
[ ] Webhooks implemented and tested
[ ] Database schema deployed
[ ] Limit enforcement working
[ ] Upgrade prompts in UI
[ ] Pricing page designed
[ ] FAQ written
[ ] Terms of Service updated
[ ] Test: Free → Pro → Cancel → Resubscribe flow
```

---

*Implement this after you have 50-100 free users and understand what they actually value.*
