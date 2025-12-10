"use client";

import { useState } from "react";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from "recharts";

interface EquityDataPoint {
  date: string;
  equity: number;
  drawdown: number;
  benchmark?: number;
}

interface Trade {
  entry_time: string;
  exit_time: string;
  side: string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  return_pct: string;
}

interface EquityChartProps {
  data: EquityDataPoint[];
  initialCapital: number;
  trades?: Trade[];
  symbol?: string;
  showBenchmark?: boolean;
}

export default function EquityChart({
  data,
  initialCapital,
  trades = [],
  symbol = "Stock",
  showBenchmark = true,
}: EquityChartProps) {
  const [displayBenchmark, setDisplayBenchmark] = useState(showBenchmark);

  if (!data || data.length === 0) return null;

  // Format data for display
  const chartData = data.map((d) => ({
    ...d,
    displayDate: new Date(d.date).toLocaleDateString("en-US", {
      month: "short",
      year: "2-digit",
    }),
    strategyReturn: ((d.equity - initialCapital) / initialCapital) * 100,
    benchmarkReturn: d.benchmark ? ((d.benchmark - initialCapital) / initialCapital) * 100 : 0,
  }));

  const allValues = [
    ...data.map((d) => d.equity),
    ...(displayBenchmark && data[0]?.benchmark ? data.map((d) => d.benchmark!) : []),
  ];
  const minEquity = Math.min(...allValues);
  const maxEquity = Math.max(...allValues);
  const padding = (maxEquity - minEquity) * 0.1;

  const formatCurrency = (value: number) => `$${value.toLocaleString()}`;

  const formatTooltipDate = (date: string) =>
    new Date(date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload;
      return (
        <div className="p-3 rounded-lg border" style={{ background: "var(--bg-secondary)", borderColor: "var(--border-color)" }}>
          <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>{formatTooltipDate(d.date)}</p>
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-4">
              <span className="text-xs" style={{ color: "var(--accent-success)" }}>Strategy:</span>
              <span className="font-semibold" style={{ color: "var(--accent-success)" }}>{formatCurrency(d.equity)}</span>
            </div>
            {displayBenchmark && d.benchmark && (
              <div className="flex items-center justify-between gap-4">
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>Buy & Hold:</span>
                <span className="font-semibold" style={{ color: "var(--text-secondary)" }}>{formatCurrency(d.benchmark)}</span>
              </div>
            )}
            <div className="pt-1 mt-1 border-t text-xs" style={{ borderColor: "var(--border-color)" }}>
              <span style={{ color: d.drawdown > 0 ? "var(--accent-danger)" : "var(--text-muted)" }}>
                Drawdown: {d.drawdown.toFixed(2)}%
              </span>
            </div>
          </div>
        </div>
      );
    }
    return null;
  };

  // Calculate returns
  const finalStrategy = data[data.length - 1]?.equity || initialCapital;
  const finalBenchmark = data[data.length - 1]?.benchmark || initialCapital;
  const strategyReturn = ((finalStrategy - initialCapital) / initialCapital) * 100;
  const benchmarkReturn = ((finalBenchmark - initialCapital) / initialCapital) * 100;
  const alpha = strategyReturn - benchmarkReturn;

  return (
    <div className="w-full h-full flex flex-col">
      {/* Chart Header */}
      <div className="flex items-center justify-between px-4 py-2">
        <h4 className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>Equity Curve</h4>
        <label className="flex items-center gap-2 text-xs cursor-pointer">
          <input
            type="checkbox"
            checked={displayBenchmark}
            onChange={(e) => setDisplayBenchmark(e.target.checked)}
            className="rounded"
          />
          <span style={{ color: "var(--text-muted)" }}>Show Buy & Hold</span>
        </label>
      </div>

      {/* Main Chart - fills available space */}
      <div className="flex-1 min-h-0 px-2">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#8fae8b" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#8fae8b" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
            <XAxis
              dataKey="displayDate"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--text-muted)", fontSize: 10 }}
              interval="preserveStartEnd"
            />
            <YAxis
              domain={[minEquity - padding, maxEquity + padding]}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--text-muted)", fontSize: 10 }}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              width={50}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={initialCapital} stroke="var(--text-muted)" strokeDasharray="3 3" strokeOpacity={0.5} />
            {displayBenchmark && (
              <Line
                type="monotone"
                dataKey="benchmark"
                stroke="var(--text-muted)"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                dot={false}
                name={`${symbol} Buy & Hold`}
              />
            )}
            <Area
              type="monotone"
              dataKey="equity"
              stroke="#6a8f66"
              strokeWidth={2}
              fill="url(#equityGradient)"
              name="Strategy"
            />
            <Legend wrapperStyle={{ fontSize: 10, color: "var(--text-muted)" }} iconType="line" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Stats Row - Always visible, consistent height */}
      <div className="grid grid-cols-3 gap-2 px-4 py-2 text-center border-t" style={{ borderColor: "var(--border-color)" }}>
        <div>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Strategy</p>
          <p className="font-bold text-sm" style={{ color: strategyReturn >= 0 ? "var(--accent-success)" : "var(--accent-danger)" }}>
            {strategyReturn >= 0 ? "+" : ""}{strategyReturn.toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Buy & Hold</p>
          <p className="font-bold text-sm" style={{ color: displayBenchmark ? (benchmarkReturn >= 0 ? "var(--text-secondary)" : "var(--accent-danger)") : "var(--text-muted)" }}>
            {displayBenchmark ? `${benchmarkReturn >= 0 ? "+" : ""}${benchmarkReturn.toFixed(1)}%` : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>Alpha</p>
          <p className="font-bold text-sm" style={{ color: displayBenchmark ? (alpha >= 0 ? "var(--accent-success)" : "var(--accent-danger)") : "var(--text-muted)" }}>
            {displayBenchmark ? `${alpha >= 0 ? "+" : ""}${alpha.toFixed(1)}%` : "—"}
          </p>
        </div>
      </div>

      {/* Drawdown Chart */}
      <div className="px-4 py-2 border-t" style={{ borderColor: "var(--border-color)" }}>
        <h4 className="text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>Drawdown</h4>
        <div style={{ height: 60 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#c88b8b" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#c88b8b" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <XAxis dataKey="displayDate" hide />
              <YAxis
                domain={["dataMin", 0]}
                axisLine={false}
                tickLine={false}
                tick={{ fill: "var(--text-muted)", fontSize: 9 }}
                tickFormatter={(v) => `${v.toFixed(0)}%`}
                width={40}
                reversed
              />
              <Area type="monotone" dataKey="drawdown" stroke="#b07070" strokeWidth={1} fill="url(#drawdownGradient)" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
