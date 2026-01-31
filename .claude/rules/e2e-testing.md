# E2E Testing Rules

## When to Use E2E Tests
- Critical user flows (backtest execution, chart interaction)
- Visual verification (markers, colors, layout)
- Integration between frontend and backend

## E2E Test Structure
```typescript
test('backtest flow shows trade markers on chart', async ({ page }) => {
  // Arrange: Navigate and setup
  await page.goto('http://localhost:3000');

  // Act: Perform user actions
  await page.click('[data-testid="run-backtest"]');
  await page.waitForSelector('[data-testid="trade-marker"]');

  // Assert: Verify expected state
  const markers = await page.$$('[data-testid="trade-marker"]');
  expect(markers.length).toBeGreaterThan(0);
});
```

## Test Selectors
- Prefer `data-testid` attributes
- Avoid CSS selectors that change with styling
- Use semantic roles where appropriate

## Wait Strategies
```typescript
// Wait for element
await page.waitForSelector('[data-testid="chart"]');

// Wait for API response
await page.waitForResponse('**/api/backtest/run');

// Wait for network idle
await page.waitForLoadState('networkidle');
```

## Screenshot Testing
```typescript
// Capture for visual regression
await expect(page).toHaveScreenshot('chart-with-trades.png');
```

## Test Isolation
- Each test starts with fresh state
- Use fixtures for common setup
- Clean up any created data

## Performance Budget
- Page load: < 3s
- Backtest API: < 5s
- Chart render: < 1s
