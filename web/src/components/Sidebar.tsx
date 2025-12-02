"use client";

import { MessageSquare, TrendingUp, Database, Github, Zap } from "lucide-react";

type View = "chat" | "strategies" | "data";

interface SidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
}

const navItems = [
  { id: "chat" as const, label: "Agent", icon: MessageSquare },
  { id: "strategies" as const, label: "Strategies", icon: TrendingUp },
  { id: "data" as const, label: "Data", icon: Database },
];

export default function Sidebar({ currentView, onViewChange }: SidebarProps) {
  return (
    <aside
      className="w-64 flex flex-col border-r"
      style={{
        background: "var(--bg-secondary)",
        borderColor: "var(--border-color)",
      }}
    >
      {/* Logo */}
      <div
        className="p-6 border-b"
        style={{ borderColor: "var(--border-color)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ background: "var(--accent-primary)" }}
          >
            <Zap size={20} style={{ color: "var(--bg-primary)" }} />
          </div>
          <div>
            <h1 className="text-lg font-bold gradient-text">Bonito</h1>
            <p
              className="text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              AI Trading Platform
            </p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          {navItems.map((item) => {
            const isActive = currentView === item.id;
            const Icon = item.icon;

            return (
              <li key={item.id}>
                <button
                  onClick={() => onViewChange(item.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all"
                  style={{
                    background: isActive ? "var(--bg-tertiary)" : "transparent",
                    color: isActive
                      ? "var(--accent-primary)"
                      : "var(--text-secondary)",
                    borderLeft: isActive
                      ? "2px solid var(--accent-primary)"
                      : "2px solid transparent",
                  }}
                >
                  <Icon size={18} />
                  <span className="font-medium">{item.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Status */}
      <div
        className="p-4 border-t"
        style={{ borderColor: "var(--border-color)" }}
      >
        <div className="card p-3">
          <div className="flex items-center justify-between mb-2">
            <span
              className="text-xs font-medium"
              style={{ color: "var(--text-muted)" }}
            >
              API Status
            </span>
            <span className="flex items-center gap-1">
              <span
                className="w-2 h-2 rounded-full animate-pulse-glow"
                style={{ background: "var(--accent-primary)" }}
              />
              <span className="text-xs" style={{ color: "var(--accent-primary)" }}>
                Connected
              </span>
            </span>
          </div>
          <p
            className="text-xs truncate"
            style={{ color: "var(--text-muted)" }}
          >
            localhost:8000
          </p>
        </div>
      </div>

      {/* Footer */}
      <div
        className="p-4 border-t"
        style={{ borderColor: "var(--border-color)" }}
      >
        <a
          href="https://github.com/dgiliver/bonito"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 text-sm transition-colors"
          style={{ color: "var(--text-muted)" }}
        >
          <Github size={16} />
          <span>View on GitHub</span>
        </a>
      </div>
    </aside>
  );
}
