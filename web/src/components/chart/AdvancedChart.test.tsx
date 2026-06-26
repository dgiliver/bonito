/**
 * AdvancedChart Component Tests
 *
 * TDD tests for the advanced charting system
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Mock lightweight-charts v5 API
vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addSeries: vi.fn(() => ({
      setData: vi.fn(),
      priceScale: vi.fn(() => ({
        applyOptions: vi.fn(),
      })),
    })),
    timeScale: vi.fn(() => ({
      fitContent: vi.fn(),
      setVisibleRange: vi.fn(),
    })),
    applyOptions: vi.fn(),
    resize: vi.fn(),
    remove: vi.fn(),
  })),
  ColorType: { Solid: "solid" },
  CandlestickSeries: {},
  HistogramSeries: {},
}));

import { AdvancedChart } from "./AdvancedChart";

// Mock fetch
const mockOHLCVData = {
  symbol: "SPY",
  interval: "1d",
  bars: [
    {
      time: 1704067200,
      open: 470,
      high: 475,
      low: 468,
      close: 473,
      volume: 1000000,
    },
    {
      time: 1704153600,
      open: 473,
      high: 478,
      low: 471,
      close: 476,
      volume: 1200000,
    },
    {
      time: 1704240000,
      open: 476,
      high: 480,
      low: 474,
      close: 478,
      volume: 900000,
    },
  ],
};

const mockSymbols = {
  results: [
    { symbol: "SPY", name: "SPDR S&P 500 ETF" },
    { symbol: "QQQ", name: "Invesco QQQ Trust" },
    { symbol: "AAPL", name: "Apple Inc." },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn((url: string) => {
    if (url.includes("/chart/ohlcv")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockOHLCVData),
      });
    }
    if (url.includes("/chart/symbols") || url.includes("/chart/search")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockSymbols),
      });
    }
    return Promise.resolve({ ok: false });
  }) as unknown as typeof fetch;
});

// =============================================================================
// 1. Rendering Tests
// =============================================================================

describe("AdvancedChart - Rendering", () => {
  it("renders the chart container", () => {
    render(<AdvancedChart />);
    expect(screen.getByTestId("advanced-chart")).toBeInTheDocument();
  });

  it("renders the chart header with controls", () => {
    render(<AdvancedChart />);
    expect(screen.getByTestId("chart-header")).toBeInTheDocument();
  });

  it("displays symbol selector", () => {
    render(<AdvancedChart initialSymbol="SPY" />);
    expect(screen.getByText("SPY")).toBeInTheDocument();
  });

  it("displays interval selector", () => {
    render(<AdvancedChart />);
    expect(screen.getByTestId("interval-selector")).toBeInTheDocument();
  });

  it("displays time range selector", () => {
    render(<AdvancedChart />);
    expect(screen.getByTestId("range-selector")).toBeInTheDocument();
  });

  it("renders chart canvas area", () => {
    render(<AdvancedChart />);
    expect(screen.getByTestId("chart-canvas")).toBeInTheDocument();
  });
});

// =============================================================================
// 2. Symbol Selection Tests
// =============================================================================

describe("AdvancedChart - Symbol Selection", () => {
  it("opens symbol search on click", async () => {
    render(<AdvancedChart initialSymbol="SPY" />);

    const symbolButton = screen.getByTestId("symbol-selector");
    fireEvent.click(symbolButton);

    await waitFor(() => {
      expect(screen.getByTestId("symbol-search")).toBeInTheDocument();
    });
  });

  it("shows available symbols in dropdown", async () => {
    render(<AdvancedChart initialSymbol="SPY" />);

    fireEvent.click(screen.getByTestId("symbol-selector"));

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
  });

  it("changes symbol on selection", async () => {
    render(<AdvancedChart initialSymbol="SPY" />);

    fireEvent.click(screen.getByTestId("symbol-selector"));

    await waitFor(() => {
      const aaplOption = screen.getByText("AAPL");
      fireEvent.click(aaplOption);
    });

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
  });
});

// =============================================================================
// 3. Interval Selection Tests
// =============================================================================

describe("AdvancedChart - Interval Selection", () => {
  it("displays current interval", () => {
    render(<AdvancedChart initialInterval="1d" />);
    const intervalSelector = screen.getByTestId("interval-selector");
    expect(intervalSelector).toHaveTextContent("1D");
  });

  it("shows interval options on click", () => {
    render(<AdvancedChart />);

    fireEvent.click(screen.getByTestId("interval-selector"));

    expect(screen.getByText("1m")).toBeInTheDocument();
    expect(screen.getByText("5m")).toBeInTheDocument();
    expect(screen.getByText("1h")).toBeInTheDocument();
  });

  it("changes interval on selection", async () => {
    render(<AdvancedChart initialInterval="1d" />);

    fireEvent.click(screen.getByTestId("interval-selector"));
    fireEvent.click(screen.getByText("1h"));

    await waitFor(() => {
      expect(screen.getByText("1h")).toBeInTheDocument();
    });
  });
});

// =============================================================================
// 4. Time Range Selection Tests
// =============================================================================

describe("AdvancedChart - Time Range", () => {
  it("displays range options", () => {
    render(<AdvancedChart />);

    expect(screen.getByTestId("range-1D")).toBeInTheDocument();
    expect(screen.getByTestId("range-1W")).toBeInTheDocument();
    expect(screen.getByTestId("range-1M")).toBeInTheDocument();
    expect(screen.getByTestId("range-1Y")).toBeInTheDocument();
  });

  it("highlights selected range", () => {
    render(<AdvancedChart initialRange="1Y" />);

    const yearButton = screen.getByTestId("range-1Y");
    expect(yearButton).toHaveClass("active");
  });

  it("changes range on click", async () => {
    render(<AdvancedChart initialRange="1Y" />);

    fireEvent.click(screen.getByTestId("range-1M"));

    await waitFor(() => {
      expect(screen.getByTestId("range-1M")).toHaveClass("active");
    });
  });
});

// =============================================================================
// 5. Trade Markers Tests
// =============================================================================

describe("AdvancedChart - Trade Markers", () => {
  const mockTrades = [
    {
      entry_time: "2024-01-02T10:00:00Z",
      exit_time: "2024-01-03T10:00:00Z",
      side: "buy",
      pnl: 500,
    },
  ];

  it("accepts trades prop", () => {
    expect(() => render(<AdvancedChart trades={mockTrades} />)).not.toThrow();
  });

  it("renders without trades", () => {
    render(<AdvancedChart />);
    expect(screen.getByTestId("advanced-chart")).toBeInTheDocument();
  });
});

// =============================================================================
// 6. Loading States Tests
// =============================================================================

describe("AdvancedChart - Loading States", () => {
  it("shows loading indicator while fetching data", () => {
    render(<AdvancedChart />);
    expect(screen.getByTestId("chart-loading")).toBeInTheDocument();
  });

  it("hides loading after data loads", async () => {
    render(<AdvancedChart />);

    await waitFor(() => {
      expect(screen.queryByTestId("chart-loading")).not.toBeInTheDocument();
    });
  });
});

// =============================================================================
// 7. Responsive Tests
// =============================================================================

describe("AdvancedChart - Responsive", () => {
  it("fills container width", () => {
    const { container } = render(<AdvancedChart />);
    const chart = container.querySelector('[data-testid="advanced-chart"]');
    expect(chart).toHaveClass("w-full");
  });

  it("fills container height", () => {
    const { container } = render(<AdvancedChart />);
    const chart = container.querySelector('[data-testid="advanced-chart"]');
    expect(chart).toHaveClass("h-full");
  });
});
