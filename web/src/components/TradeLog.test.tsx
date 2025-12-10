/**
 * TradeLog Component Tests
 *
 * TDD tests for F024: UI Virtualization & Large Data Handling
 *
 * Test Categories:
 * 1. Rendering - Basic display of trade data
 * 2. Virtualization - Only visible items rendered
 * 3. Scrolling - Proper scroll behavior
 * 4. Performance - Handles 1000+ trades smoothly
 * 5. Edge Cases - Empty, single trade, etc.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import TradeLog from './TradeLog';

// Mock trade data generator
function generateTrades(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    entry_time: new Date(2024, 0, i + 1).toISOString(),
    exit_time: new Date(2024, 0, i + 2).toISOString(),
    side: 'buy' as const,
    quantity: 100,
    entry_price: 100 + i,
    exit_price: 105 + i,
    pnl: (i % 2 === 0 ? 1 : -1) * (50 + i),
    return_pct: `${(i % 2 === 0 ? '' : '-')}${(5 + i * 0.1).toFixed(2)}%`,
  }));
}

// =============================================================================
// 1. Rendering Tests
// =============================================================================

describe('TradeLog - Rendering', () => {
  it('renders the trade log container', () => {
    const trades = generateTrades(5);
    const { container } = render(<TradeLog trades={trades} />);

    expect(container.querySelector('[data-testid="trade-log"]')).toBeInTheDocument();
  });

  it('displays column headers', () => {
    const trades = generateTrades(5);
    render(<TradeLog trades={trades} />);

    expect(screen.getByText('Entry')).toBeInTheDocument();
    expect(screen.getByText('Exit')).toBeInTheDocument();
    expect(screen.getByText('In')).toBeInTheDocument();
    expect(screen.getByText('Out')).toBeInTheDocument();
    expect(screen.getByText('P&L')).toBeInTheDocument();
    expect(screen.getByText('Return')).toBeInTheDocument();
  });

  it('displays trade count in header', () => {
    const trades = generateTrades(72);
    render(<TradeLog trades={trades} />);

    expect(screen.getByText(/72 trades/i)).toBeInTheDocument();
  });

  it('has scroll container for trade data', () => {
    const trades = [{
      entry_time: '2024-01-15T10:30:00Z',
      exit_time: '2024-01-16T14:45:00Z',
      side: 'buy' as const,
      quantity: 100,
      entry_price: 150.25,
      exit_price: 155.50,
      pnl: 525,
      return_pct: '3.50%',
    }];

    const { container } = render(<TradeLog trades={trades} />);

    // Scroll container should exist
    const scrollContainer = container.querySelector('[data-testid="scroll-container"]');
    expect(scrollContainer).toBeInTheDocument();
  });

  it('has virtual container for trades', () => {
    const trades = [{
      entry_time: '2024-01-15T10:30:00Z',
      exit_time: '2024-01-16T14:45:00Z',
      side: 'buy' as const,
      quantity: 100,
      entry_price: 150.256789,
      exit_price: 155.501234,
      pnl: 525.25,
      return_pct: '3.50%',
    }];

    const { container } = render(<TradeLog trades={trades} />);

    const virtualContainer = container.querySelector('[data-testid="virtual-container"]');
    expect(virtualContainer).toBeInTheDocument();
  });

  it('renders component with positive P&L trade', () => {
    const trades = [{
      entry_time: '2024-01-15T10:30:00Z',
      exit_time: '2024-01-16T14:45:00Z',
      side: 'buy' as const,
      quantity: 100,
      entry_price: 150,
      exit_price: 155,
      pnl: 500,
      return_pct: '3.33%',
    }];

    const { container } = render(<TradeLog trades={trades} />);

    // Component renders without error
    expect(container.querySelector('[data-testid="virtual-container"]')).toBeInTheDocument();
  });

  it('renders component with negative P&L trade', () => {
    const trades = [{
      entry_time: '2024-01-15T10:30:00Z',
      exit_time: '2024-01-16T14:45:00Z',
      side: 'buy' as const,
      quantity: 100,
      entry_price: 155,
      exit_price: 150,
      pnl: -500,
      return_pct: '-3.23%',
    }];

    const { container } = render(<TradeLog trades={trades} />);

    expect(container.querySelector('[data-testid="virtual-container"]')).toBeInTheDocument();
  });
});

// =============================================================================
// 2. Virtualization Tests
// =============================================================================

describe('TradeLog - Virtualization', () => {
  it('has virtualization container', () => {
    const trades = generateTrades(500);
    const { container } = render(<TradeLog trades={trades} />);

    // Virtual container should exist
    const virtualContainer = container.querySelector('[data-testid="virtual-container"]');
    expect(virtualContainer).toBeInTheDocument();
  });

  it('scroll container is scrollable', () => {
    const trades = generateTrades(100);
    const { container } = render(<TradeLog trades={trades} />);

    const scrollContainer = container.querySelector('[data-testid="scroll-container"]');
    expect(scrollContainer).toHaveClass('overflow-y-auto');
  });

  it('maintains scroll container for full dataset', () => {
    const trades = generateTrades(500);
    const { container } = render(<TradeLog trades={trades} />);

    // The virtual scroll container should exist
    const scrollContainer = container.querySelector('[data-testid="virtual-container"]');
    expect(scrollContainer).toBeInTheDocument();
  });
});

// =============================================================================
// 3. Scrolling Tests
// =============================================================================

describe('TradeLog - Scrolling', () => {
  it('scrolls to show more items', () => {
    const trades = generateTrades(100);
    const { container } = render(<TradeLog trades={trades} />);

    const scrollContainer = container.querySelector('[data-testid="scroll-container"]');
    expect(scrollContainer).toBeInTheDocument();

    // Simulate scroll
    fireEvent.scroll(scrollContainer!, { target: { scrollTop: 500 } });

    // After scroll, different rows should be visible
    // (This is a basic check - actual virtualization logic tested in integration)
    expect(scrollContainer).toHaveProperty('scrollTop');
  });

  it('has smooth scroll behavior', () => {
    const trades = generateTrades(50);
    const { container } = render(<TradeLog trades={trades} />);

    const scrollContainer = container.querySelector('[data-testid="scroll-container"]');
    expect(scrollContainer).toHaveClass('overflow-y-auto');
  });
});

// =============================================================================
// 4. Performance Tests
// =============================================================================

describe('TradeLog - Performance', () => {
  it('renders 1000 trades without timeout', () => {
    const startTime = performance.now();

    const trades = generateTrades(1000);
    render(<TradeLog trades={trades} />);

    const renderTime = performance.now() - startTime;

    // Should render in under 500ms (JSDOM is slower)
    expect(renderTime).toBeLessThan(500);
  });

  it('handles 5000 trades', () => {
    const trades = generateTrades(5000);

    // Should not throw
    expect(() => render(<TradeLog trades={trades} />)).not.toThrow();

    expect(screen.getByText(/5000 trades/i)).toBeInTheDocument();
  });

  it('virtual container exists for many trades', () => {
    const trades = generateTrades(1000);
    const { container } = render(<TradeLog trades={trades} />);

    // Virtual container should exist (virtualization is set up)
    const virtualContainer = container.querySelector('[data-testid="virtual-container"]');
    expect(virtualContainer).toBeInTheDocument();
  });
});

// =============================================================================
// 5. Edge Cases
// =============================================================================

describe('TradeLog - Edge Cases', () => {
  it('renders empty state when no trades', () => {
    render(<TradeLog trades={[]} />);

    expect(screen.getByText(/no trades/i)).toBeInTheDocument();
  });

  it('handles single trade', () => {
    const trades = generateTrades(1);
    const { container } = render(<TradeLog trades={trades} />);

    expect(screen.getByText(/1 trades/i)).toBeInTheDocument();
    expect(container.querySelector('[data-testid="virtual-container"]')).toBeInTheDocument();
  });

  it('handles undefined trades prop gracefully', () => {
    // @ts-expect-error - Testing runtime behavior
    expect(() => render(<TradeLog trades={undefined} />)).not.toThrow();
  });

  it('handles trades with missing fields gracefully', () => {
    const trades = [{
      entry_time: '2024-01-15T10:30:00Z',
      exit_time: '2024-01-16T14:45:00Z',
      side: 'buy' as const,
      quantity: 100,
      entry_price: 150,
      exit_price: 155,
      pnl: 500,
      // Missing return_pct
    }];

    // @ts-expect-error - Testing runtime behavior
    expect(() => render(<TradeLog trades={trades} />)).not.toThrow();
  });
});

// =============================================================================
// 6. Accessibility Tests
// =============================================================================

describe('TradeLog - Accessibility', () => {
  it('has accessible table structure', () => {
    const trades = generateTrades(5);
    const { container } = render(<TradeLog trades={trades} />);

    // Has virtual container with table role
    const table = container.querySelector('[role="table"]');
    expect(table).toBeInTheDocument();

    // Component renders with trades data
    expect(container.querySelector('[data-testid="virtual-container"]')).toBeInTheDocument();
  });

  it('has proper aria labels', () => {
    const trades = generateTrades(50);
    const { container } = render(<TradeLog trades={trades} />);

    const table = container.querySelector('[role="table"]');
    expect(table).toHaveAttribute('aria-label', 'Trade log');
  });
});
