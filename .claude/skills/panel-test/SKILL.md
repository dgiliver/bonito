---
name: panel-test
description: Comprehensive panel testing skill for indicator panels. Tests single panels, combinations, ordering, and crosshair sync.
allowed-tools: Bash, Read, Grep, Glob, mcp__Claude_in_Chrome__*
---

# Panel Test Skill

Run comprehensive tests on indicator panels to verify rendering, data persistence, and synchronization.

## Usage

```bash
/panel-test <indicator>
/panel-test <indicator1> --then <indicator2>
/panel-test --full-matrix
```

## Examples

### Single Panel Test
```bash
/panel-test macd
```
Tests:
- MACD panel renders with blue/orange lines and histogram
- Values update on crosshair hover
- Panel removes cleanly

### Sequential Panel Test
```bash
/panel-test macd --then rsi
```
Tests:
- Add MACD first, verify it works
- Add RSI second, verify MACD still has data
- Verify RSI appears BELOW MACD (user add order)
- Verify crosshair syncs both panels

### Full Matrix Test
```bash
/panel-test --full-matrix
```
Runs all combinations:
- MACD alone
- RSI alone
- Stoch alone
- MACD → RSI
- RSI → MACD
- MACD → Stoch
- RSI → Stoch
- MACD → RSI → Stoch

## Test Protocol

### 1. Pre-Flight
```bash
# Ensure servers running
curl -s http://localhost:8000/health
curl -s http://localhost:3000
```

### 2. Navigate to Chart
```
1. Open http://localhost:3000
2. Wait for chart to load (candlesticks visible)
3. Clear any existing panels
```

### 3. Add Panel via Agent Chat
```
Type in agent chat: "Add <indicator> indicator"
Wait for panel to appear (check for new div below chart)
```

### 4. Verify Panel Content

**MACD Panel:**
- [ ] Blue MACD line visible
- [ ] Orange signal line visible
- [ ] Green/red histogram bars visible
- [ ] Label shows "MACD(12,26,9)"

**RSI Panel:**
- [ ] Purple line visible
- [ ] Overbought line at 70
- [ ] Oversold line at 30
- [ ] Label shows "RSI(14)"

**Stochastic Panel:**
- [ ] Blue %K line visible
- [ ] Orange %D line visible
- [ ] Overbought/oversold zones
- [ ] Label shows "Stoch(14,3,3)"

### 5. Crosshair Test
```
1. Move cursor over price chart
2. Move cursor over each panel
3. Verify: Crosshair appears in ALL panels simultaneously
4. Verify: Legend values update in real-time
```

### 6. Data Persistence Test
```
1. With panels visible, add another panel
2. Verify: First panel's data did NOT disappear
3. Move cursor between panels rapidly
4. Verify: All data remains visible
```

### 7. Ordering Test
```
1. Note the order panels were added
2. Verify: Visual order matches add order (top to bottom)
3. Verify: Last added panel has time scale
```

## Known Bugs to Watch For

### Bug: Panel Data Disappears
**Symptom**: Lines/histogram vanish when cursor moves
**Cause**: Missing React state for crosshair-updated values
**Check**: Does panel use `useState` for current values?

### Bug: Wrong Panel Order
**Symptom**: Panels appear in fixed order regardless of add sequence
**Cause**: Hardcoded render order instead of `activePanels.map()`
**Check**: Is ChartContainer using dynamic rendering?

### Bug: Time Scale on Wrong Panel
**Symptom**: Time scale appears on panel that isn't last
**Cause**: Incorrect `isLastPanel` calculation
**Check**: Is `showTimeScale` based on array index?

### Bug: Undefined Config Values
**Symptom**: Label shows "MACD(undefined,undefined,undefined)"
**Cause**: Config not passed correctly to panel
**Check**: Is config prop drilling working?

## Test Report Template

```markdown
## Panel Test Report

**Date**: [YYYY-MM-DD HH:MM]
**Test Type**: [single/sequential/matrix]
**Panel(s)**: [list]

### Results

| Check | Status | Notes |
|-------|--------|-------|
| Panel renders | ✅/❌ | |
| Data visible | ✅/❌ | |
| Crosshair sync | ✅/❌ | |
| Order correct | ✅/❌ | |
| Time scale correct | ✅/❌ | |
| Values update | ✅/❌ | |

### Screenshots
- Initial state: [link/description]
- After add: [link/description]
- Crosshair hover: [link/description]

### Issues Found
- [List any bugs]

### Verdict
✅ PASS / ❌ FAIL: [summary]
```

## Integration with Ralph Loop

For automated comprehensive testing:

```bash
/ralph-loop "Panel testing matrix:
1. Start servers (make api & make web)
2. For each indicator in [macd, rsi, stoch]:
   a. Add indicator
   b. Verify panel renders
   c. Move crosshair, verify values update
   d. Clear panel
3. For each combination:
   a. Add first indicator
   b. Add second indicator
   c. Verify BOTH have data
   d. Verify order matches add sequence
   e. Clear panels
4. Take screenshots at each step
5. Generate test report
Output <promise>PANEL_MATRIX_COMPLETE</promise>" --max-iterations 40
```

## Recovery Steps

If tests fail:

1. **Check console** for JavaScript errors
2. **Check network** for failed API calls
3. **Verify** servers are running on correct ports
4. **Clear** browser cache and retry
5. **Read** the panel component source for recent changes
6. **Compare** to working panel (RSIPanel) for patterns
