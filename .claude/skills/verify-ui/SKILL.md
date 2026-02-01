---
name: verify-ui
description: Quick visual verification of UI changes. Start servers, take screenshots, check for regressions.
allowed-tools: Bash, Read, mcp__Claude_in_Chrome__*
---

# Verify UI Skill

Quick visual verification after frontend changes.

## Usage

```bash
/verify-ui              # Full verification
/verify-ui chart        # Chart-specific
/verify-ui panels       # Indicator panels
/verify-ui agent        # Agent chat
/verify-ui trades       # Trade markers and panel
```

## Quick Verification Protocol

### 1. Ensure Servers Running
```bash
# Check if running
curl -s http://localhost:8000/health && echo "API OK" || echo "API DOWN"
curl -s http://localhost:3000 > /dev/null && echo "Web OK" || echo "Web DOWN"

# Start if needed
cd /Users/dgiliver/personal_projects/bonito && make api &
sleep 2
cd /Users/dgiliver/personal_projects/bonito/web && npm run dev &
sleep 5
```

### 2. Navigate and Screenshot
```
1. Open http://localhost:3000
2. Wait for full load (no spinners)
3. Take baseline screenshot
```

### 3. Verification Checklist

**Chart Component:**
- [ ] Candlesticks render (not blank)
- [ ] Volume bars visible at bottom
- [ ] Price axis shows values
- [ ] Time axis shows dates
- [ ] Crosshair appears on hover
- [ ] OHLCV values update in header

**Indicator Panels:**
- [ ] Panel appears below price chart
- [ ] Lines/histogram visible
- [ ] Label shows indicator name
- [ ] Values update on hover
- [ ] Panel order matches add order

**Agent Chat:**
- [ ] Input field visible
- [ ] Context chips show (symbol, interval)
- [ ] Responses stream properly
- [ ] Tool usage feedback appears

**Trade View:**
- [ ] Markers appear on chart
- [ ] Green = long entry/exit
- [ ] Red = short entry/exit
- [ ] Click marker shows details
- [ ] Trade panel updates

## Visual Regression Checkpoints

Take screenshots at these moments:

| Checkpoint | What to Check |
|------------|---------------|
| Initial Load | Chart renders, no errors |
| Symbol Change | Data updates, axis scales |
| Add Indicator | Panel appears, data visible |
| Run Backtest | Markers appear, no crash |
| Crosshair Move | Values update, smooth motion |
| Zoom In/Out | All elements scale properly |

## Common Issues

### Blank Chart
1. Check console for errors
2. Verify API is serving data
3. Check network tab for failed requests
4. Verify DuckDB has data: `bonito data list`

### Indicator Not Showing
1. Verify backend calculation exists
2. Check AnalysisContext.activePanels
3. Verify ChartContainer renders panel
4. Check for JavaScript errors

### Styling Broken
1. Clear browser cache
2. Verify Tailwind classes correct
3. Check for CSS conflicts
4. Verify dark mode compatibility

### Performance Issues
1. Check for infinite re-renders (React DevTools)
2. Verify no massive data arrays in state
3. Check network tab for repeated calls
4. Profile with Chrome DevTools

## Report Format

```markdown
## UI Verification Report

**Time**: [timestamp]
**Area**: [chart/panels/agent/trades/full]
**Build**: [npm run build status]

### Screenshot Summary
- Initial: [description/pass/fail]
- After changes: [description/pass/fail]

### Checklist Results
- [x] Charts render correctly
- [x] Indicators work
- [ ] Issue: [describe]

### Console Errors
None / [list any]

### Network Errors
None / [list any]

### Verdict
✅ READY / ⚠️ MINOR ISSUES / ❌ BLOCKING ISSUES

### Next Steps
[If issues found]
```

## Integration with CI

For automated verification:

```bash
# Run Playwright visual tests
cd web && npx playwright test tests/visual/

# Update snapshots if intentional changes
cd web && npx playwright test --update-snapshots
```

## Ralph Loop for Comprehensive Testing

```bash
/ralph-loop "Comprehensive UI verification:
1. Start servers
2. Navigate to http://localhost:3000
3. Take screenshot of initial state
4. Click through each main feature:
   a. Change symbol (SPY → AAPL)
   b. Add MACD indicator
   c. Add RSI indicator
   d. Run a backtest
   e. Click on a trade marker
5. For each step:
   - Take screenshot
   - Check console for errors
   - Check network for failures
6. Generate verification report
Output <promise>UI_VERIFIED</promise>" --max-iterations 20
```
