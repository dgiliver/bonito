"use client";

import {
  MessageSquare,
  TrendingUp,
  Database,
  Github,
  Zap,
  PanelLeftClose,
  PanelLeft,
  CandlestickChart,
  Sparkles,
  Bot,
} from "lucide-react";

type View = "chat" | "analysis" | "strategies" | "chart" | "data" | "trading";

interface SidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const navItems = [
  {
    id: "analysis" as const,
    label: "Analysis",
    icon: Sparkles,
    description: "Chart + AI",
  },
  {
    id: "chat" as const,
    label: "Agent",
    icon: MessageSquare,
    description: "Chat only",
  },
  {
    id: "strategies" as const,
    label: "Strategies",
    icon: TrendingUp,
    description: "Backtest",
  },
  {
    id: "trading" as const,
    label: "Trading",
    icon: Bot,
    description: "Live bots",
  },
  {
    id: "chart" as const,
    label: "Chart",
    icon: CandlestickChart,
    description: "View only",
  },
  { id: "data" as const, label: "Data", icon: Database, description: "Manage" },
];

export default function Sidebar({
  currentView,
  onViewChange,
  collapsed,
  onToggleCollapse,
}: SidebarProps) {
  return (
    <aside
      className="flex flex-col border-r transition-all duration-300 ease-in-out"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--border-color)",
        width: collapsed ? "64px" : "220px",
        minWidth: collapsed ? "64px" : "220px",
      }}
    >
      {/* Logo */}
      <div
        className="p-3 border-b flex items-center justify-between"
        style={{ borderColor: "var(--border-color)" }}
      >
        <div className="flex items-center gap-2 overflow-hidden">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ background: "var(--accent-primary)" }}
          >
            <Zap size={18} style={{ color: "var(--bg-primary)" }} />
          </div>
          {!collapsed && (
            <div className="overflow-hidden">
              <h1 className="text-base font-bold gradient-text whitespace-nowrap">
                Bonito
              </h1>
            </div>
          )}
        </div>
        <button
          onClick={onToggleCollapse}
          className="p-1.5 rounded-md transition-colors hover:bg-[var(--bg-tertiary)]"
          style={{ color: "var(--text-muted)" }}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const isActive = currentView === item.id;
            const Icon = item.icon;

            return (
              <li key={item.id}>
                <button
                  onClick={() => onViewChange(item.id)}
                  className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg transition-all"
                  style={{
                    background: isActive ? "var(--bg-tertiary)" : "transparent",
                    color: isActive
                      ? "var(--accent-primary)"
                      : "var(--text-secondary)",
                    justifyContent: collapsed ? "center" : "flex-start",
                  }}
                  title={collapsed ? item.label : undefined}
                >
                  <Icon size={18} className="flex-shrink-0" />
                  {!collapsed && (
                    <span className="font-medium text-sm">{item.label}</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Status - only when expanded */}
      {!collapsed && (
        <div
          className="p-2 border-t"
          style={{ borderColor: "var(--border-color)" }}
        >
          <div
            className="px-3 py-2 rounded-lg"
            style={{ background: "var(--bg-tertiary)" }}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                API
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="w-1.5 h-1.5 rounded-full animate-pulse-glow"
                  style={{ background: "var(--accent-primary)" }}
                />
                <span
                  className="text-xs"
                  style={{ color: "var(--accent-primary)" }}
                >
                  Connected
                </span>
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <div
        className="p-2 border-t"
        style={{ borderColor: "var(--border-color)" }}
      >
        <a
          href="https://github.com/dgiliver/bonito"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors hover:bg-[var(--bg-tertiary)]"
          style={{
            color: "var(--text-muted)",
            justifyContent: collapsed ? "center" : "flex-start",
          }}
          title={collapsed ? "View on GitHub" : undefined}
        >
          <Github size={16} className="flex-shrink-0" />
          {!collapsed && <span>GitHub</span>}
        </a>
      </div>
    </aside>
  );
}
