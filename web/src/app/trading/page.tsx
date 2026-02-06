"use client";

import { BotDashboard } from "@/components/trading";
import { TradingProvider } from "@/contexts/TradingContext";

export default function TradingPage() {
  return (
    <TradingProvider>
      <main
        className="min-h-screen"
        style={{ background: "var(--bg-primary)" }}
      >
        <BotDashboard />
      </main>
    </TradingProvider>
  );
}
