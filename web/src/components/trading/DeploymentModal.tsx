"use client";

import { useState, useEffect } from "react";
import { useTrading, DeploymentConfig } from "@/contexts/TradingContext";
import { RiskWarningModal } from "./RiskWarningModal";
import { X, Rocket, AlertTriangle, Clock, Zap, Calendar } from "lucide-react";

// Calculate risk score client-side for preview
function calculateRiskScore(config: {
  mode: "paper" | "live";
  max_position_pct: number;
  max_daily_loss_pct?: number;
  has_stop_loss?: boolean;
}): { score: "low" | "medium" | "high" | "extreme"; warnings: string[] } {
  const warnings: string[] = [];
  let points = 0;

  // Position size warnings
  if (config.max_position_pct > 50) {
    warnings.push("Large position size (>50% of portfolio per trade)");
    points += 2;
  }
  if (config.max_position_pct > 90) {
    warnings.push("Extreme position size (>90% of portfolio per trade)");
    points += 3;
  }

  // No daily loss limit
  if (!config.max_daily_loss_pct) {
    warnings.push("No daily loss limit - bot won't auto-stop on bad days");
    points += 1;
  }

  // Live trading
  if (config.mode === "live") {
    warnings.push("LIVE TRADING - Real money at risk");
    points += 2;
  }

  // Determine score
  let score: "low" | "medium" | "high" | "extreme";
  if (points >= 6) score = "extreme";
  else if (points >= 4) score = "high";
  else if (points >= 2) score = "medium";
  else score = "low";

  return { score, warnings };
}

export function DeploymentModal() {
  const { deployBot, state, closeDeploymentModal } = useTrading();
  const { isDeploying, account, deploymentModalOpen, pendingDeployment } =
    state;

  // Form state
  const [mode, setMode] = useState<"paper" | "live">("paper");
  const [executionModel, setExecutionModel] = useState<
    "scheduled" | "continuous" | "event_driven"
  >("continuous");
  const [schedule, setSchedule] = useState("0 9 * * 1-5"); // 9am weekdays
  const [maxPositionPct, setMaxPositionPct] = useState(10);
  const [maxDailyLossPct, setMaxDailyLossPct] = useState<number | undefined>(5);
  const [acknowledgeRisks, setAcknowledgeRisks] = useState(false);

  // Risk warning modal
  const [showRiskWarning, setShowRiskWarning] = useState(false);

  // Calculate risk preview
  const riskPreview = calculateRiskScore({
    mode,
    max_position_pct: maxPositionPct,
    max_daily_loss_pct: maxDailyLossPct,
  });

  // Reset form when modal opens
  // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional: reset form state when modal opens
  useEffect(() => {
    if (deploymentModalOpen) {
      setMode("paper");
      setExecutionModel("continuous");
      setMaxPositionPct(pendingDeployment?.max_position_pct ?? 10);
      setMaxDailyLossPct(pendingDeployment?.max_daily_loss_pct ?? 5);
      setAcknowledgeRisks(false);
    }
  }, [deploymentModalOpen, pendingDeployment]);

  const handleDeploy = async () => {
    if (!pendingDeployment?.strategy_name) return;

    // Show risk warning for high/extreme risk
    if (
      (riskPreview.score === "high" || riskPreview.score === "extreme") &&
      !acknowledgeRisks
    ) {
      setShowRiskWarning(true);
      return;
    }

    const config: DeploymentConfig = {
      strategy_name: pendingDeployment.strategy_name,
      strategy_config: pendingDeployment.strategy_config ?? {},
      mode,
      execution_model: executionModel,
      schedule: executionModel === "scheduled" ? schedule : undefined,
      max_position_pct: maxPositionPct,
      max_daily_loss_pct: maxDailyLossPct,
      acknowledge_risks: acknowledgeRisks,
    };

    try {
      await deployBot(config);
    } catch (error) {
      console.error("Deployment failed:", error);
    }
  };

  const handleRiskAccept = () => {
    setAcknowledgeRisks(true);
    setShowRiskWarning(false);
    // Retry deployment after acknowledgment
    handleDeploy();
  };

  if (!deploymentModalOpen) return null;

  const riskScoreColors = {
    low: { bg: "rgba(34, 197, 94, 0.1)", text: "var(--accent-success)" },
    medium: { bg: "rgba(234, 179, 8, 0.1)", text: "var(--accent-warning)" },
    high: { bg: "rgba(249, 115, 22, 0.1)", text: "#f97316" },
    extreme: { bg: "rgba(239, 68, 68, 0.1)", text: "var(--accent-danger)" },
  };

  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center"
        style={{ background: "rgba(0, 0, 0, 0.6)" }}
      >
        <div
          className="w-full max-w-lg rounded-xl shadow-2xl mx-4"
          style={{ background: "var(--bg-primary)" }}
        >
          {/* Header */}
          <div
            className="px-6 py-4 border-b flex items-center justify-between"
            style={{ borderColor: "var(--border-color)" }}
          >
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-lg flex items-center justify-center"
                style={{ background: "var(--bg-tertiary)" }}
              >
                <Rocket size={20} style={{ color: "var(--accent-primary)" }} />
              </div>
              <div>
                <h2
                  className="text-lg font-semibold"
                  style={{ color: "var(--text-primary)" }}
                >
                  Deploy Trading Bot
                </h2>
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  Configure and launch your strategy
                </p>
              </div>
            </div>
            <button
              onClick={closeDeploymentModal}
              className="p-2 rounded-lg transition-colors hover:bg-[var(--bg-secondary)]"
              style={{ color: "var(--text-muted)" }}
            >
              <X size={20} />
            </button>
          </div>

          <div className="p-6 max-h-[70vh] overflow-y-auto">
            {/* Strategy Info */}
            <div
              className="mb-6 rounded-lg p-4"
              style={{ background: "var(--bg-secondary)" }}
            >
              <h3
                className="font-medium"
                style={{ color: "var(--text-primary)" }}
              >
                {pendingDeployment?.strategy_name || "Unnamed Strategy"}
              </h3>
              {typeof pendingDeployment?.strategy_config?.description ===
                "string" && (
                <p
                  className="mt-1 text-sm"
                  style={{ color: "var(--text-muted)" }}
                >
                  {pendingDeployment.strategy_config.description}
                </p>
              )}
            </div>

            {/* Account Status */}
            {!account.linked && (
              <div
                className="mb-4 rounded-lg border p-3 flex items-center gap-2"
                style={{
                  borderColor: "var(--accent-warning)",
                  background: "rgba(234, 179, 8, 0.1)",
                }}
              >
                <AlertTriangle
                  size={18}
                  style={{ color: "var(--accent-warning)" }}
                />
                <p
                  className="text-sm"
                  style={{ color: "var(--accent-warning)" }}
                >
                  No Alpaca account linked. Please link an account first.
                </p>
              </div>
            )}

            {/* Mode Selection */}
            <div className="mb-5">
              <label
                className="mb-2 block text-sm font-medium"
                style={{ color: "var(--text-secondary)" }}
              >
                Trading Mode
              </label>
              <div className="flex gap-3">
                <button
                  onClick={() => setMode("paper")}
                  className="flex-1 p-3 rounded-lg border-2 transition-all"
                  style={{
                    borderColor:
                      mode === "paper"
                        ? "var(--accent-primary)"
                        : "var(--border-color)",
                    background:
                      mode === "paper"
                        ? "rgba(59, 130, 246, 0.1)"
                        : "transparent",
                  }}
                >
                  <div
                    className="font-medium"
                    style={{
                      color:
                        mode === "paper"
                          ? "var(--accent-primary)"
                          : "var(--text-secondary)",
                    }}
                  >
                    Paper Trading
                  </div>
                  <div
                    className="text-xs mt-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Safe simulation mode
                  </div>
                </button>
                <button
                  onClick={() => setMode("live")}
                  className="flex-1 p-3 rounded-lg border-2 transition-all"
                  style={{
                    borderColor:
                      mode === "live"
                        ? "var(--accent-danger)"
                        : "var(--border-color)",
                    background:
                      mode === "live"
                        ? "rgba(239, 68, 68, 0.1)"
                        : "transparent",
                  }}
                >
                  <div
                    className="font-medium"
                    style={{
                      color:
                        mode === "live"
                          ? "var(--accent-danger)"
                          : "var(--text-secondary)",
                    }}
                  >
                    Live Trading
                  </div>
                  <div
                    className="text-xs mt-1"
                    style={{ color: "var(--text-muted)" }}
                  >
                    Real money at risk
                  </div>
                </button>
              </div>
            </div>

            {/* Execution Model */}
            <div className="mb-5">
              <label
                className="mb-2 block text-sm font-medium"
                style={{ color: "var(--text-secondary)" }}
              >
                Execution Model
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { value: "continuous", label: "Continuous", icon: Zap },
                  { value: "scheduled", label: "Scheduled", icon: Calendar },
                  { value: "event_driven", label: "Event", icon: Clock },
                ].map((option) => (
                  <button
                    key={option.value}
                    onClick={() =>
                      setExecutionModel(
                        option.value as
                          | "scheduled"
                          | "continuous"
                          | "event_driven",
                      )
                    }
                    className="p-2 rounded-lg border text-center transition-all"
                    style={{
                      borderColor:
                        executionModel === option.value
                          ? "var(--accent-primary)"
                          : "var(--border-color)",
                      background:
                        executionModel === option.value
                          ? "rgba(59, 130, 246, 0.1)"
                          : "transparent",
                    }}
                  >
                    <option.icon
                      size={18}
                      className="mx-auto mb-1"
                      style={{
                        color:
                          executionModel === option.value
                            ? "var(--accent-primary)"
                            : "var(--text-muted)",
                      }}
                    />
                    <div
                      className="text-xs font-medium"
                      style={{
                        color:
                          executionModel === option.value
                            ? "var(--accent-primary)"
                            : "var(--text-secondary)",
                      }}
                    >
                      {option.label}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Schedule (if scheduled) */}
            {executionModel === "scheduled" && (
              <div className="mb-5">
                <label
                  className="mb-2 block text-sm font-medium"
                  style={{ color: "var(--text-secondary)" }}
                >
                  Schedule (Cron)
                </label>
                <input
                  type="text"
                  value={schedule}
                  onChange={(e) => setSchedule(e.target.value)}
                  className="w-full rounded-lg border p-2.5 text-sm"
                  style={{
                    borderColor: "var(--border-color)",
                    background: "var(--bg-secondary)",
                    color: "var(--text-primary)",
                  }}
                  placeholder="0 9 * * 1-5"
                />
                <p
                  className="mt-1 text-xs"
                  style={{ color: "var(--text-muted)" }}
                >
                  Example: &quot;0 9 * * 1-5&quot; = 9:00 AM weekdays
                </p>
              </div>
            )}

            {/* Position Size */}
            <div className="mb-5">
              <div className="flex items-center justify-between mb-2">
                <label
                  className="text-sm font-medium"
                  style={{ color: "var(--text-secondary)" }}
                >
                  Max Position Size
                </label>
                <span
                  className="text-sm font-semibold"
                  style={{ color: "var(--accent-primary)" }}
                >
                  {maxPositionPct}%
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={100}
                value={maxPositionPct}
                onChange={(e) => setMaxPositionPct(Number(e.target.value))}
                className="w-full accent-[var(--accent-primary)]"
              />
              <div
                className="flex justify-between text-xs mt-1"
                style={{ color: "var(--text-muted)" }}
              >
                <span>1% (Conservative)</span>
                <span>100% (Aggressive)</span>
              </div>
            </div>

            {/* Daily Loss Limit */}
            <div className="mb-5">
              <label
                className="mb-2 flex items-center text-sm font-medium cursor-pointer"
                style={{ color: "var(--text-secondary)" }}
              >
                <input
                  type="checkbox"
                  checked={maxDailyLossPct !== undefined}
                  onChange={(e) =>
                    setMaxDailyLossPct(e.target.checked ? 5 : undefined)
                  }
                  className="mr-2 accent-[var(--accent-primary)]"
                />
                Daily Loss Limit (Circuit Breaker)
              </label>
              {maxDailyLossPct !== undefined && (
                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="number"
                    min={0.1}
                    max={50}
                    step={0.1}
                    value={maxDailyLossPct}
                    onChange={(e) => setMaxDailyLossPct(Number(e.target.value))}
                    className="w-20 rounded-lg border p-2 text-sm"
                    style={{
                      borderColor: "var(--border-color)",
                      background: "var(--bg-secondary)",
                      color: "var(--text-primary)",
                    }}
                  />
                  <span
                    className="text-sm"
                    style={{ color: "var(--text-muted)" }}
                  >
                    % max daily loss
                  </span>
                </div>
              )}
            </div>

            {/* Risk Score Preview */}
            <div
              className="rounded-lg border p-4"
              style={{ borderColor: "var(--border-color)" }}
            >
              <div className="flex items-center justify-between mb-2">
                <span
                  className="text-sm font-medium"
                  style={{ color: "var(--text-secondary)" }}
                >
                  Risk Assessment
                </span>
                <span
                  className="rounded-full px-3 py-1 text-xs font-semibold"
                  style={{
                    background: riskScoreColors[riskPreview.score].bg,
                    color: riskScoreColors[riskPreview.score].text,
                  }}
                >
                  {riskPreview.score.toUpperCase()}
                </span>
              </div>
              {riskPreview.warnings.length > 0 && (
                <ul className="space-y-1.5">
                  {riskPreview.warnings.map((warning, i) => (
                    <li
                      key={i}
                      className="flex items-start text-sm"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <AlertTriangle
                        size={14}
                        className="mr-2 mt-0.5 flex-shrink-0"
                        style={{ color: "var(--accent-warning)" }}
                      />
                      {warning}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Actions */}
          <div
            className="px-6 py-4 border-t flex justify-end gap-3"
            style={{
              borderColor: "var(--border-color)",
              background: "var(--bg-secondary)",
            }}
          >
            <button
              onClick={closeDeploymentModal}
              disabled={isDeploying}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              style={{
                border: "1px solid var(--border-color)",
                color: "var(--text-secondary)",
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleDeploy}
              disabled={
                isDeploying ||
                !pendingDeployment?.strategy_name ||
                !account.linked
              }
              className="px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
              style={{
                background:
                  isDeploying ||
                  !pendingDeployment?.strategy_name ||
                  !account.linked
                    ? "var(--bg-tertiary)"
                    : "var(--accent-primary)",
                color:
                  isDeploying ||
                  !pendingDeployment?.strategy_name ||
                  !account.linked
                    ? "var(--text-muted)"
                    : "var(--bg-primary)",
                opacity:
                  isDeploying ||
                  !pendingDeployment?.strategy_name ||
                  !account.linked
                    ? 0.6
                    : 1,
              }}
            >
              <Rocket size={16} />
              {isDeploying ? "Deploying..." : "Deploy Bot"}
            </button>
          </div>
        </div>
      </div>

      {/* Risk Warning Modal */}
      <RiskWarningModal
        isOpen={showRiskWarning}
        onCancel={() => setShowRiskWarning(false)}
        onAccept={handleRiskAccept}
        riskScore={riskPreview.score}
        warnings={riskPreview.warnings}
      />
    </>
  );
}
