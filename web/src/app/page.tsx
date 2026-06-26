"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { Sidebar } from "@/components/Sidebar";
import { Chat, Message } from "@/components/Chat";
import { Strategies } from "@/components/Strategies";
import { Data } from "@/components/Data";
import { BotDashboard } from "@/components/trading";
import { TradingProvider } from "@/contexts/TradingContext";

// Dynamically import chart components to avoid SSR issues with lightweight-charts
const AdvancedChart = dynamic(
  () => import("@/components/chart/AdvancedChart").then((m) => m.AdvancedChart),
  {
    ssr: false,
    loading: () => (
      <div
        className="flex items-center justify-center h-full"
        style={{ background: "var(--bg-primary)" }}
      >
        <div
          className="animate-spin rounded-full h-8 w-8 border-2 border-t-transparent"
          style={{ borderColor: "var(--accent-primary)" }}
        />
      </div>
    ),
  },
);

// Unified Analysis View - combines chart + AI assistant
const AnalysisView = dynamic(
  () => import("@/components/analysis/AnalysisView").then((m) => m.AnalysisView),
  {
    ssr: false,
    loading: () => (
      <div
        className="flex items-center justify-center h-full"
        style={{ background: "var(--bg-primary)" }}
      >
        <div
          className="animate-spin rounded-full h-8 w-8 border-2 border-t-transparent"
          style={{ borderColor: "var(--accent-primary)" }}
        />
      </div>
    ),
  },
);

type View = "chat" | "analysis" | "strategies" | "chart" | "data" | "trading";

export default function Home() {
  const [currentView, setCurrentView] = useState<View>("analysis");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Lift chat state to preserve across view switches
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);

  // Sync sidebar state from localStorage after hydration (must be in useEffect to avoid hydration mismatch)
  useEffect(() => {
    const saved = localStorage.getItem("sidebar-collapsed");
    if (saved) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Required for hydration-safe localStorage sync
      setSidebarCollapsed(JSON.parse(saved));
    }
  }, []);

  const toggleSidebar = () => {
    const newState = !sidebarCollapsed;
    setSidebarCollapsed(newState);
    localStorage.setItem("sidebar-collapsed", JSON.stringify(newState));
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        currentView={currentView}
        onViewChange={setCurrentView}
        collapsed={sidebarCollapsed}
        onToggleCollapse={toggleSidebar}
      />
      <main className="flex-1 overflow-hidden transition-all duration-300">
        {currentView === "analysis" && <AnalysisView />}
        {currentView === "chat" && (
          <Chat
            messages={messages}
            setMessages={setMessages}
            sessionId={sessionId}
            setSessionId={setSessionId}
          />
        )}
        {currentView === "strategies" && <Strategies />}
        {currentView === "chart" && (
          <div className="h-full" style={{ background: "var(--bg-primary)" }}>
            <AdvancedChart />
          </div>
        )}
        {currentView === "data" && <Data />}
        {currentView === "trading" && (
          <TradingProvider>
            <BotDashboard />
          </TradingProvider>
        )}
      </main>
    </div>
  );
}
