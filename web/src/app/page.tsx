"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import Sidebar from "@/components/Sidebar";
import Chat, { Message } from "@/components/Chat";
import Strategies from "@/components/Strategies";
import Data from "@/components/Data";

// Dynamically import chart components to avoid SSR issues with lightweight-charts
const AdvancedChart = dynamic(
  () => import("@/components/chart/AdvancedChart"),
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
  () => import("@/components/analysis/AnalysisView"),
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

type View = "chat" | "analysis" | "strategies" | "chart" | "data";

// Initialize sidebar state from localStorage (client-side only)
const getInitialSidebarState = () => {
  if (typeof window === "undefined") return false;
  const saved = localStorage.getItem("sidebar-collapsed");
  return saved ? JSON.parse(saved) : false;
};

export default function Home() {
  const [currentView, setCurrentView] = useState<View>("analysis");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    getInitialSidebarState,
  );

  // Lift chat state to preserve across view switches
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);

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
      </main>
    </div>
  );
}
