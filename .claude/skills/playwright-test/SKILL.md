---
name: playwright-test
description: "Headless Playwright testing with 3 parallel agents: validation, edge-case, and stress/performance. Use after any UI or backend change to verify correctness, boundary conditions, and performance."
---

# Playwright Test — Three-Agent Headless Testing

Runs three specialized testing agents **in parallel** using headless Playwright against Bonito's frontend and API. Each agent has a distinct focus and produces an independent report. The combined result gives full coverage: correctness, resilience, and performance.

## Usage

```
/playwright-test                    # Full three-agent sweep
/playwright-test validation         # Only validation agent
/playwright-test edge               # Only edge-case agent
/playwright-test stress             # Only stress/performance agent
/playwright-test <area>             # Area: chart, panels, agent, trades, backtest, api
```

## Architecture

```
/playwright-test
    │
    ├── Agent 1: VALIDATION (correctness)
    │   "Does everything render and function correctly?"
    │
    ├── Agent 2: EDGE CASE (boundaries)
    │   "What breaks under unusual conditions?"
    │
    └── Agent 3: STRESS & PERFORMANCE (limits)
        "How does it behave under load and at scale?"

All three run in PARALLEL using headless Chromium.
All scripts written to /tmp/pw-test-*.py (auto-cleaned).
All screenshots saved to /tmp/pw-screenshots/ for review.
```

## CRITICAL: Execution Rules

1. **Always headless**: Use `headless=True` for all browser launches
2. **Always wait for networkidle**: Before any DOM inspection
3. **Screenshots on failure**: Capture state when assertions fail
4. **Scripts in /tmp**: Never write test files into the project
5. **Server management**: Use `webapp-testing` skill's `with_server.py` if servers aren't running
6. **Parallel launch**: Spawn all three agents simultaneously via the Agent tool
7. **Independent reports**: Each agent produces its own verdict

## Pre-Flight (run before spawning agents)

```bash
# Check servers
curl -s http://localhost:8000/health && echo "API: UP" || echo "API: DOWN"
curl -s http://localhost:3000 > /dev/null 2>&1 && echo "WEB: UP" || echo "WEB: DOWN"

# Start if needed (use webapp-testing's with_server.py or manual)
# API: cd /Users/dgiliver/personal_projects/bonito && make api &
# Web: cd /Users/dgiliver/personal_projects/bonito/web && npm run dev &

# Create screenshot directory
mkdir -p /tmp/pw-screenshots
```

If servers are down, start them using:
```bash
python ~/.claude/skills/webapp-testing/scripts/with_server.py \
  --server "cd /Users/dgiliver/personal_projects/bonito && uvicorn bonito.api.main:app --host 0.0.0.0 --port 8000" --port 8000 \
  --server "cd /Users/dgiliver/personal_projects/bonito/web && npm run dev" --port 3000 \
  -- python /tmp/pw-test-runner.py
```

---

## Agent 1: VALIDATION MODE

**Purpose**: Verify that all core functionality works correctly. This is the "green path" — does the app do what it should?

**Spawn as**: `Agent(subagent_type="ui-explorer", description="Validation mode testing")`

### Test Protocol

Write a Python Playwright script to `/tmp/pw-test-validation.py` that tests:

#### 1.1 Chart Rendering
```python
# Navigate to localhost:3000, wait for networkidle
# Assert: canvas element exists (lightweight-charts renders to canvas)
# Assert: no console errors on load
# Screenshot: /tmp/pw-screenshots/val-01-chart-load.png
```

#### 1.2 Price Data Display
```python
# Assert: price axis has numeric values (not empty)
# Assert: time axis has dates
# Assert: candlestick data points are visible (canvas not blank)
# Hover over chart center
# Assert: OHLCV header updates with values
# Screenshot: /tmp/pw-screenshots/val-02-price-data.png
```

#### 1.3 Symbol Switching
```python
# Find symbol selector/input
# Change symbol (SPY -> AAPL if available, else verify SPY)
# Wait for data reload (networkidle)
# Assert: chart re-renders with new data
# Assert: no console errors
# Screenshot: /tmp/pw-screenshots/val-03-symbol-switch.png
```

#### 1.4 Indicator Panel Addition
```python
# Locate indicator controls (add MACD)
# Wait for panel to appear below chart
# Assert: MACD panel element exists
# Assert: MACD panel has canvas with rendered data
# Add RSI indicator
# Assert: RSI panel appears BELOW MACD (user add order preserved)
# Assert: MACD data still visible (not disappeared)
# Assert: time scale only on last (bottom) panel
# Screenshot: /tmp/pw-screenshots/val-04-panels.png
```

#### 1.5 Crosshair Synchronization
```python
# Move mouse across price chart
# Assert: crosshair line appears
# Assert: all indicator panels show synchronized crosshair
# Assert: legend values update in each panel
# Screenshot: /tmp/pw-screenshots/val-05-crosshair.png
```

#### 1.6 Agent Chat
```python
# Find chat input
# Assert: input field is visible and focusable
# Assert: context chips visible (symbol, interval)
# Screenshot: /tmp/pw-screenshots/val-06-chat.png
```

#### 1.7 API Health
```python
# Fetch /health endpoint
# Assert: 200 status
# Fetch /api/data/symbols (or equivalent list endpoint)
# Assert: response contains symbol data
# Screenshot: not needed (API only)
```

### Validation Report Format
```
VALIDATION REPORT
═══════════════════════════════════════
Test                        Status
───────────────────────────────────────
Chart Rendering             PASS/FAIL
Price Data Display          PASS/FAIL
Symbol Switching            PASS/FAIL
Indicator Panels            PASS/FAIL
Crosshair Sync              PASS/FAIL
Agent Chat UI               PASS/FAIL
API Health                  PASS/FAIL
───────────────────────────────────────
Console Errors:             [count]
Network Errors:             [count]
Screenshots:                /tmp/pw-screenshots/val-*.png
───────────────────────────────────────
VERDICT: PASS / FAIL ([N]/7 passed)
═══════════════════════════════════════
```

---

## Agent 2: EDGE CASE MODE

**Purpose**: Test boundary conditions, unusual inputs, rapid interactions, and states that normal users might not hit but that break apps.

**Spawn as**: `Agent(subagent_type="ui-explorer", description="Edge case testing")`

### Test Protocol

Write a Python Playwright script to `/tmp/pw-test-edge.py` that tests:

#### 2.1 Rapid Panel Add/Remove
```python
# Add MACD, RSI, Stochastic in rapid succession (< 500ms between each)
# Assert: all three panels render correctly
# Remove middle panel (RSI)
# Assert: MACD and Stochastic still render
# Assert: time scale moves to Stochastic (new last panel)
# Re-add RSI
# Assert: RSI appears at bottom (new add order)
# Screenshot: /tmp/pw-screenshots/edge-01-rapid-panels.png
```

#### 2.2 Zoom Extremes
```python
# Zoom in to maximum (only a few bars visible)
# Assert: no rendering errors, axis labels still readable
# Zoom out to maximum (all data visible)
# Assert: no rendering errors, chart doesn't overflow
# Screenshot both states: /tmp/pw-screenshots/edge-02-zoom-*.png
```

#### 2.3 Viewport Resize Stress
```python
# Start at 1920x1080
# Resize to 800x600
# Assert: chart reflows, no overlapping elements
# Resize to 400x300 (extreme small)
# Assert: no crash, elements still accessible
# Resize back to 1920x1080
# Assert: layout restored correctly
# Screenshot: /tmp/pw-screenshots/edge-03-resize.png
```

#### 2.4 Empty/Missing Data States
```python
# Navigate with a symbol that has no data (if testable)
# Or check behavior when API returns empty dataset
# Assert: graceful empty state, no crash
# Assert: appropriate message shown (not blank screen)
# Screenshot: /tmp/pw-screenshots/edge-04-empty.png
```

#### 2.5 Concurrent User Actions
```python
# While chart is loading data, try to:
#   - Add an indicator
#   - Change symbol
#   - Open chat
# Assert: no race condition crashes
# Assert: final state is consistent
# Screenshot: /tmp/pw-screenshots/edge-05-concurrent.png
```

#### 2.6 Panel State After Navigation
```python
# Add 2 indicators
# Navigate away from analysis view (if other views exist)
# Navigate back
# Assert: panels either persist or cleanly reset
# Assert: no phantom panels or ghost data
# Screenshot: /tmp/pw-screenshots/edge-06-navigation.png
```

#### 2.7 Chat Edge Cases
```python
# Send empty message
# Assert: no crash, input handles gracefully
# Send very long message (500+ characters)
# Assert: input handles, no overflow
# Send special characters (<script>, SQL injection patterns)
# Assert: sanitized, no XSS
# Screenshot: /tmp/pw-screenshots/edge-07-chat-edge.png
```

#### 2.8 Browser Back/Forward
```python
# Perform several actions (add panel, change symbol)
# Hit browser back
# Assert: no crash, state handles gracefully
# Hit browser forward
# Assert: consistent state
# Screenshot: /tmp/pw-screenshots/edge-08-history.png
```

### Edge Case Report Format
```
EDGE CASE REPORT
═══════════════════════════════════════
Test                        Status
───────────────────────────────────────
Rapid Panel Add/Remove      PASS/FAIL
Zoom Extremes               PASS/FAIL
Viewport Resize             PASS/FAIL
Empty Data States           PASS/FAIL
Concurrent Actions          PASS/FAIL
Navigation State            PASS/FAIL
Chat Edge Cases             PASS/FAIL
Browser History             PASS/FAIL
───────────────────────────────────────
Console Errors:             [count]
Crashes Detected:           [count]
Race Conditions:            [count]
Screenshots:                /tmp/pw-screenshots/edge-*.png
───────────────────────────────────────
VERDICT: PASS / FAIL ([N]/8 passed)
RESILIENCE SCORE: [N]/10
═══════════════════════════════════════
```

---

## Agent 3: STRESS & PERFORMANCE MODE

**Purpose**: Measure rendering performance, memory behavior, API response times, and behavior under load. Find performance regressions.

**Spawn as**: `Agent(subagent_type="ui-explorer", description="Stress and performance testing")`

### Test Protocol

Write a Python Playwright script to `/tmp/pw-test-stress.py` that tests:

#### 3.1 Page Load Performance
```python
# Measure time from navigation start to networkidle
# Measure time to first contentful paint (via Performance API)
# Measure time to chart render (canvas has data)
# Assert: page load < 3s
# Assert: chart render < 2s
# Record: exact timings for comparison
```

#### 3.2 API Response Times
```python
# Intercept network requests via page.route or page.on('response')
# Measure response time for:
#   - /health
#   - /api/data/bars (or equivalent data endpoint)
#   - Any backtest endpoint if triggered
# Assert: health < 100ms
# Assert: data endpoint < 2s
# Assert: backtest endpoint < 5s
# Record: p50, p95, p99 if multiple calls made
```

#### 3.3 Rapid Interaction Stress
```python
# Move mouse across chart at high speed (50+ events)
# Measure: frame drops, console errors during rapid movement
# Rapidly click through indicator add/remove 10 times
# Assert: no memory leaks (check JS heap via CDP)
# Assert: no accumulated console errors
# Record: interaction latency
```

#### 3.4 Multi-Panel Rendering Performance
```python
# Add panels one by one: MACD, RSI, Stochastic
# Measure render time for each panel addition
# Assert: each panel renders < 500ms
# With 3 panels active, measure crosshair sync latency
# Assert: sync < 50ms between panels
# Screenshot: /tmp/pw-screenshots/stress-04-multi-panel.png
```

#### 3.5 Memory Profile
```python
# Use CDP (Chrome DevTools Protocol) to measure JS heap
# Record baseline heap after page load
# Perform 20 panel add/remove cycles
# Record heap after cycles
# Assert: heap growth < 50% of baseline (no major leak)
# Perform 50 symbol switches (if multiple symbols available)
# Record heap after switches
# Assert: heap growth reasonable
```

#### 3.6 Large Dataset Handling
```python
# If possible, load a symbol with maximum available data
# Measure chart render time with full dataset
# Zoom to full extent
# Assert: no significant lag
# Scroll/pan across full dataset
# Assert: smooth interaction (no freezes > 500ms)
# Record: frame timings
```

#### 3.7 Concurrent API Requests
```python
# Fire 10 simultaneous API requests
# Measure: all return successfully
# Assert: no 5xx errors
# Assert: avg response time doesn't degrade > 2x single request
# Record: concurrency metrics
```

#### 3.8 CSS/Layout Thrashing Detection
```python
# Monitor for forced reflows during interactions
# Use Performance Observer or CDP Performance domain
# Assert: no layout thrashing during crosshair movement
# Assert: no forced synchronous layouts during panel operations
```

### Stress & Performance Report Format
```
STRESS & PERFORMANCE REPORT
═══════════════════════════════════════
Metric                      Value     Budget    Status
────────────────────────────────────────────────────────
Page Load                   [X]ms     3000ms    PASS/FAIL
Chart Render                [X]ms     2000ms    PASS/FAIL
Panel Add (avg)             [X]ms     500ms     PASS/FAIL
Crosshair Sync              [X]ms     50ms      PASS/FAIL
API /health                 [X]ms     100ms     PASS/FAIL
API /data                   [X]ms     2000ms    PASS/FAIL
API Concurrent (10x)        [X]ms     4000ms    PASS/FAIL
───────────────────────────────────────────────────────
Memory                      Value     Threshold Status
───────────────────────────────────────────────────────
Baseline Heap               [X]MB     -         -
After 20 Panel Cycles       [X]MB     +50%      PASS/FAIL
After 50 Interactions       [X]MB     +100%     PASS/FAIL
───────────────────────────────────────────────────────
Stability
───────────────────────────────────────────────────────
Console Errors (load):      [count]
Console Errors (interact):  [count]
Crashes:                    [count]
Layout Thrash Events:       [count]
───────────────────────────────────────────────────────
Screenshots:                /tmp/pw-screenshots/stress-*.png
───────────────────────────────────────────────────────
VERDICT: PASS / FAIL
PERFORMANCE SCORE: [N]/10
═══════════════════════════════════════
```

---

## Combined Report

After all three agents complete, synthesize:

```
THREE-AGENT TEST REPORT
═══════════════════════════════════════════════════════
Agent              Verdict    Score     Issues
───────────────────────────────────────────────────────
VALIDATION         PASS/FAIL  [N]/7    [summary]
EDGE CASE          PASS/FAIL  [N]/8    [summary]
STRESS/PERF        PASS/FAIL  [N]/10   [summary]
───────────────────────────────────────────────────────
OVERALL VERDICT:   READY / NEEDS WORK / BLOCKING
Screenshots:       /tmp/pw-screenshots/
Console Errors:    [total count across all agents]
═══════════════════════════════════════════════════════

BLOCKING ISSUES:
  [list any failures that must be fixed]

WARNINGS:
  [list any non-blocking concerns]

NEXT STEPS:
  [recommended actions]
```

## Playwright Script Template

All agents should use this base template for their scripts:

```python
#!/usr/bin/env python3
"""Bonito Playwright Test - [MODE NAME]"""
import json
import time
from playwright.sync_api import sync_playwright

RESULTS = []
SCREENSHOTS_DIR = "/tmp/pw-screenshots"
BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"

def record(test_name: str, passed: bool, details: str = "", timing_ms: float = 0):
    RESULTS.append({
        "test": test_name,
        "status": "PASS" if passed else "FAIL",
        "details": details,
        "timing_ms": round(timing_ms, 2)
    })
    symbol = "PASS" if passed else "FAIL"
    print(f"  [{symbol}] {test_name}" + (f" ({timing_ms:.0f}ms)" if timing_ms else ""))
    if details:
        print(f"        {details}")

def screenshot(page, name: str):
    path = f"{SCREENSHOTS_DIR}/{name}.png"
    page.screenshot(path=path, full_page=True)
    return path

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()

    # Collect console errors
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    try:
        # ... test logic here ...
        pass
    finally:
        browser.close()

    # Print summary
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    total = len(RESULTS)
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed")
    print(f"Console errors: {len(console_errors)}")
    if console_errors:
        for err in console_errors[:5]:
            print(f"  - {err[:120]}")
    print(f"{'='*50}")
```

## Integration with Existing Skills

This skill composes with Bonito's existing testing infrastructure:

| Existing Skill/Agent | How It Relates |
|---|---|
| `/verify-ui` | Quick manual check (this skill replaces it for automated flows) |
| `chart-validator` agent | Deep chart-specific validation (this skill subsumes it for headless) |
| `/panel-test` | Panel-specific testing (this skill's validation mode covers panels) |
| `webapp-testing` skill | Server management (`with_server.py`) — used by this skill |
| `playwright-skill` | Raw automation — this skill uses it for execution |
| `/autoresearch:fix` | If tests fail, pipe failures into autoresearch fix loop |

## Autoresearch Integration

After a failing test run, automatically fix issues:

```
/autoresearch:fix "Fix all failing Playwright tests from /tmp/pw-test-results.json.
Scope: web/src/components/analysis/
Metric: All 3 test agents pass (validation 7/7, edge 8/8, stress 10/10)
Verify: Run /playwright-test and check combined verdict is READY"
```
