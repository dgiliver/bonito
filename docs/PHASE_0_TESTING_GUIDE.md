# Phase 0 Testing Guide

**Purpose**: Comprehensive manual testing guide to verify Phase 0 OOP architecture foundation is working correctly.

**Prerequisites**:
- Backend API running (`make dev` or `uvicorn src.bonito.api.server:app`)
- Frontend running (`cd web && npm run dev`)
- Navigate to the analysis page

---

## 1. Basic Indicator Functionality

### Test: Add/Remove Indicators via Agent

1. **Add SMA via Agent**:
   - Type: "Add a 20-period SMA to the chart"
   - **Expected**: Blue line appears on price chart
   - **Verify**: Line follows price movement, updates on zoom/pan

2. **Add EMA via Agent**:
   - Type: "Add a 12-period EMA"
   - **Expected**: Orange line appears on price chart
   - **Verify**: Both SMA and EMA visible, different colors

3. **Add RSI via Agent**:
   - Type: "Add RSI with period 14"
   - **Expected**:
     - Purple line appears in separate panel below price chart
     - Horizontal dashed lines at 70 (red) and 30 (green)
     - Right-side price scale shows 0-100 range

4. **Add Bollinger Bands via Agent**:
   - Type: "Add Bollinger Bands with period 20"
   - **Expected**: Three lines appear (upper red dashed, middle blue, lower red dashed)

5. **Remove Indicator via Agent**:
   - Type: "Remove the SMA indicator"
   - **Expected**: Only SMA disappears, others remain

6. **Clear All Indicators**:
   - Type: "Clear all indicators"
   - **Expected**: All indicators removed, only price chart remains

---

## 2. Crosshair Value Display

### Test: Top-Left Legend (Price Chart Area)

1. **Hover over price chart**:
   - Move mouse over candlesticks
   - **Expected**: Top-left legend shows:
     - Date
     - Price: $XXX.XX
     - Volume: X.XXM (if volume visible)
     - SMA(20): XX.XX (if SMA added)
     - EMA(12): XX.XX (if EMA added)
     - BB(20) Middle: XX.XX (if BB added)

2. **Values update on hover**:
   - Move mouse across different dates
   - **Expected**: All values update dynamically
   - **Verify**: Values match the indicator lines at that timestamp

### Test: Right-Side Price Scale (Panel Indicators)

1. **Hover over RSI panel**:
   - Move mouse into the RSI panel area (bottom section)
   - **Expected**:
     - RSI value appears in right-side price scale area (bottom 30%)
     - Value updates as you move mouse
     - Color changes: Red if >70, Green if <30, Purple otherwise

2. **Hover back to price chart**:
   - Move mouse back to price chart area
   - **Expected**: RSI value disappears from right side, appears in top-left legend

---

## 3. Indicator Rendering on Zoom/Pan

### Test: Data Persistence

1. **Add SMA(20)**
2. **Zoom in** (scroll wheel or drag)
3. **Expected**: SMA line remains visible and updates correctly
4. **Pan left/right** (drag chart)
5. **Expected**: SMA line continues to render correctly
6. **Zoom out** to see more data
7. **Expected**: SMA line extends correctly, no gaps

### Test: Multiple Indicators

1. **Add SMA(20), EMA(12), RSI(14), BB(20)**
2. **Zoom and pan extensively**
3. **Expected**: All indicators remain visible and update correctly
4. **Verify**: No flickering, no missing data points

---

## 4. Agent Integration

### Test: Agent Awareness

1. **Add RSI(14)**
2. **Ask agent**: "What's the current RSI value?"
3. **Expected**: Agent responds with current RSI value and analysis

4. **Add SMA(20) and EMA(12)**
5. **Ask agent**: "What indicators are active on the chart?"
6. **Expected**: Agent lists all active indicators with their current values

### Test: Agent Control

1. **Ask agent**: "Add a 50-period SMA"
2. **Expected**: New SMA(50) appears on chart
3. **Ask agent**: "Remove the 20-period SMA"
4. **Expected**: Only SMA(20) removed, SMA(50) remains

---

## 5. Edge Cases

### Test: Rapid Add/Remove

1. **Quickly add and remove indicators**:
   - Type: "Add SMA" → Wait 1 second → "Remove SMA" → "Add EMA" → "Remove EMA"
2. **Expected**: No crashes, no duplicate indicators, clean state

### Test: Invalid Parameters

1. **Ask agent**: "Add SMA with period 0"
2. **Expected**: Either error message or default period (20) used
3. **Verify**: Chart doesn't break

### Test: Multiple Same-Type Indicators

1. **Add SMA(20)**
2. **Add SMA(50)**
3. **Expected**: Both SMAs visible with different colors/names
4. **Verify**: Both appear in top-left legend when hovering

### Test: Insufficient Data

1. **Switch to 1-minute interval with 1-day range**
2. **Add SMA(200)** (requires 200 bars)
3. **Expected**: Either no line appears or error message
4. **Verify**: Chart doesn't crash

---

## 6. Chart Resize

### Test: Container Resize

1. **Add multiple indicators** (SMA, EMA, RSI)
2. **Resize browser window** or collapse/expand agent panel
3. **Expected**:
   - Chart resizes correctly
   - All indicators remain visible
   - No rendering artifacts

---

## 7. Integration with Trades

### Test: Trades + Indicators

1. **Run a backtest** (via agent: "Run a backtest on SPY with a simple SMA crossover strategy")
2. **Add SMA(20)** to the chart
3. **Expected**:
   - Trade markers (entry/exit) appear on chart
   - SMA line visible
   - Both coexist without overlap issues
4. **Hover over trade entry point**:
   - **Expected**: Top-left legend shows price, volume, SMA value at that point

### Test: Trade Highlighting

1. **Run a backtest**
2. **Click on a trade** in the trade log
3. **Expected**:
   - Trade highlighted (gold color, larger marker)
   - Chart zooms to show entry and exit
   - Indicators remain visible during zoom

---

## 8. Performance

### Test: Many Indicators

1. **Add**: SMA(20), SMA(50), EMA(12), EMA(26), RSI(14), BB(20), BB(50)
2. **Expected**:
   - All render correctly
   - Smooth interaction (no lag)
   - Crosshair updates quickly

---

## 9. Cleanup

### Test: Clear Everything

1. **Add multiple indicators**
2. **Run a backtest** (so trades are visible)
3. **Type**: "Clear everything"
4. **Expected**:
   - All indicators removed
   - Trades remain visible (or cleared if that's the intent)
   - Chart returns to base state (price only)
   - No crashes

---

## 10. Visual Verification Checklist

- [ ] Indicator lines are smooth (no jagged edges)
- [ ] Colors match expected (SMA=blue, EMA=orange, RSI=purple, etc.)
- [ ] RSI panel has correct threshold lines (70 red, 30 green)
- [ ] Bollinger Bands has 3 lines (upper, middle, lower)
- [ ] Top-left legend is readable (good contrast, proper spacing)
- [ ] Right-side price scale values are visible (RSI, etc.)
- [ ] No visual glitches when adding/removing indicators
- [ ] Chart doesn't flicker during updates

---

## Expected Issues to Watch For

1. **Indicators not appearing**: Check browser console for errors
2. **Values not updating on hover**: Check crosshair subscription
3. **Indicators disappear on zoom**: Check data recalculation
4. **Agent can't see indicators**: Check `buildAgentContext()` in registry
5. **Type errors**: Run `npm run build` to check TypeScript

---

## Success Criteria

✅ All indicators add/remove correctly
✅ Crosshair values display correctly in appropriate locations
✅ Indicators persist through zoom/pan
✅ Agent can see and control indicators
✅ No crashes or visual glitches
✅ Performance is smooth with multiple indicators
✅ Trades and indicators coexist properly

---

## Next Steps After Phase 0

Once Phase 0 is verified, proceed to:
- **Phase 1**: Panel detection, crosshair separation
- **Phase 2**: Additional overlay indicators (VWAP, etc.)
- **Phase 3**: Additional panel indicators (MACD, Stochastic, ADX, ATR)
