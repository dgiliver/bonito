---
name: ralph
description: Start an autonomous Ralph Wiggum loop for iterative development
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
---

# Ralph Wiggum Loop Skill

Start an autonomous development loop that iterates until completion.

## Usage

```bash
/ralph "<task description>" [--max-iterations N]
```

## Examples

### UI Component Development
```bash
/ralph-loop "Build StochasticPanel component:
- Display %K and %D lines
- Overbought (80) and oversold (20) zones
- Match existing RSIPanel patterns
- Tests: cd web && npm run test:run
- All tests passing
Output <promise>STOCH_DONE</promise>" --max-iterations 25
```

### Bug Fix with Tests
```bash
/ralph-loop "Fix chart resize flickering:
1. Identify resize handling in ChartContainer.tsx
2. Implement debounced resize handler
3. Verify no flicker on window resize
4. Tests passing
Output <promise>RESIZE_FIXED</promise>" --max-iterations 15
```

### Backend Feature
```bash
/ralph-loop "Implement short selling in backtest engine:
- Add side field to Rule model
- Update P&L calculation for shorts
- Stop loss works correctly for shorts
- Run: make test
- All tests pass
Output <promise>SHORTS_DONE</promise>" --max-iterations 30
```

## Best Practices

1. **Always set --max-iterations** - Prevents runaway costs
2. **Include verification commands** - `npm test`, `make test`
3. **Reference existing patterns** - "Match RSIPanel style"
4. **Clear completion criteria** - Specific, measurable outcomes
5. **Escape hatch in prompt** - What to do if stuck after N iterations

## When to Use Ralph

**Good for:**
- Implementing defined components with tests
- Bug fixes with automated verification
- Features with clear acceptance criteria

**Avoid for:**
- Design decisions (needs human input)
- Complex refactors (too many moving parts)
- Exploratory work (unclear goals)

## Cost Control

Typical iteration costs:
- Simple task: ~$0.10-0.30 per iteration
- Complex task: ~$0.50-1.00 per iteration

Set `--max-iterations` based on complexity:
- Bug fix: 10-15 iterations
- Small feature: 15-25 iterations
- Medium feature: 25-40 iterations
