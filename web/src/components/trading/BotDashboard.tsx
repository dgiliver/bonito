"use client";

import { useState } from "react";
import { BotCard } from "./BotCard";
import { DeploymentModal } from "./DeploymentModal";
import { AccountLinkingModal } from "./AccountLinkingModal";
import { BotDetailView } from "./BotDetailView";
import { useTrading } from "@/contexts/TradingContext";
import { Loader2, Bot, Plus, AlertCircle, Link2 } from "lucide-react";

export function BotDashboard() {
  const {
    state,
    pauseBot,
    resumeBot,
    stopBot,
    linkAccount,
    openDeploymentModal,
  } = useTrading();

  const { bots, isLoading, error, account } = state;

  // Local modal state
  const [showLinkAccountModal, setShowLinkAccountModal] = useState(false);
  const [selectedBotForDetail, setSelectedBotForDetail] = useState<
    string | null
  >(null);

  const selectedBot = bots.find((bot) => bot.id === selectedBotForDetail);

  if (isLoading && bots.length === 0) {
    return (
      <div
        className="flex items-center justify-center h-full p-8"
        style={{ background: "var(--bg-primary)" }}
      >
        <div className="flex items-center gap-3">
          <Loader2
            className="animate-spin"
            size={24}
            style={{ color: "var(--accent-primary)" }}
          />
          <span style={{ color: "var(--text-muted)" }}>Loading bots...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="flex items-center justify-center h-full p-8"
        style={{ background: "var(--bg-primary)" }}
      >
        <div className="flex items-center gap-3">
          <AlertCircle size={24} style={{ color: "var(--accent-danger)" }} />
          <span style={{ color: "var(--accent-danger)" }}>{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-auto p-6"
      style={{ background: "var(--bg-primary)" }}
    >
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ background: "var(--bg-tertiary)" }}
          >
            <Bot size={20} style={{ color: "var(--accent-primary)" }} />
          </div>
          <div>
            <h1
              className="text-xl font-bold"
              style={{ color: "var(--text-primary)" }}
            >
              Trading Bots
            </h1>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {bots.length} bot{bots.length !== 1 ? "s" : ""} deployed
              {account.linked && account.account_type && (
                <span className="ml-2">
                  • {account.account_type === "paper" ? "Paper" : "Live"}{" "}
                  Trading
                </span>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* Account Status */}
          {account.linked ? (
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
              style={{ background: "var(--bg-secondary)" }}
            >
              <span
                className="w-2 h-2 rounded-full"
                style={{
                  background:
                    account.account_type === "paper"
                      ? "var(--accent-warning)"
                      : "var(--accent-success)",
                }}
              />
              <span style={{ color: "var(--text-secondary)" }}>
                {account.api_key_preview}
              </span>
              {account.buying_power && (
                <span style={{ color: "var(--text-muted)" }}>
                  | ${account.buying_power.toLocaleString()}
                </span>
              )}
            </div>
          ) : (
            <button
              onClick={() => setShowLinkAccountModal(true)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors"
              style={{
                background: "var(--bg-secondary)",
                color: "var(--text-secondary)",
                border: "1px solid var(--border-color)",
              }}
            >
              <Link2 size={14} />
              Link Alpaca Account
            </button>
          )}
          <button
            onClick={() => openDeploymentModal()}
            disabled={!account.linked}
            className="flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors"
            style={{
              background: account.linked
                ? "var(--accent-primary)"
                : "var(--bg-tertiary)",
              color: account.linked ? "var(--bg-primary)" : "var(--text-muted)",
              opacity: account.linked ? 1 : 0.6,
            }}
            title={!account.linked ? "Link Alpaca account first" : undefined}
          >
            <Plus size={18} />
            Deploy Bot
          </button>
        </div>
      </div>

      {/* Bot Grid */}
      {bots.length === 0 ? (
        <div
          className="rounded-xl border-2 border-dashed p-12 text-center"
          style={{ borderColor: "var(--border-color)" }}
        >
          <div
            className="w-16 h-16 mx-auto mb-4 rounded-xl flex items-center justify-center"
            style={{ background: "var(--bg-tertiary)" }}
          >
            <Bot size={32} style={{ color: "var(--text-muted)" }} />
          </div>
          <p
            className="text-lg font-medium mb-2"
            style={{ color: "var(--text-primary)" }}
          >
            No trading bots deployed yet
          </p>
          <p className="mb-6" style={{ color: "var(--text-muted)" }}>
            {account.linked
              ? "Create a strategy and deploy it to start automated trading."
              : "Link your Alpaca account to start deploying trading bots."}
          </p>
          {account.linked ? (
            <button
              onClick={() => openDeploymentModal()}
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium transition-colors"
              style={{
                background: "var(--accent-primary)",
                color: "var(--bg-primary)",
              }}
            >
              <Plus size={18} />
              Deploy Your First Bot
            </button>
          ) : (
            <button
              onClick={() => setShowLinkAccountModal(true)}
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium transition-colors"
              style={{
                background: "var(--accent-primary)",
                color: "var(--bg-primary)",
              }}
            >
              <Link2 size={18} />
              Link Alpaca Account
            </button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {bots.map((bot) => (
            <BotCard
              key={bot.id}
              bot={bot}
              onPause={() => pauseBot(bot.id)}
              onResume={() => resumeBot(bot.id)}
              onStop={() => stopBot(bot.id)}
              onViewDetails={() => setSelectedBotForDetail(bot.id)}
            />
          ))}
        </div>
      )}

      {/* Deployment Modal */}
      <DeploymentModal />

      {/* Account Linking Modal */}
      <AccountLinkingModal
        isOpen={showLinkAccountModal}
        onClose={() => setShowLinkAccountModal(false)}
        onLink={linkAccount}
      />

      {/* Bot Detail View */}
      {selectedBot && (
        <BotDetailView
          bot={selectedBot}
          isOpen={!!selectedBotForDetail}
          onClose={() => setSelectedBotForDetail(null)}
          onPause={() => pauseBot(selectedBot.id)}
          onResume={() => resumeBot(selectedBot.id)}
          onStop={() => stopBot(selectedBot.id)}
        />
      )}
    </div>
  );
}
