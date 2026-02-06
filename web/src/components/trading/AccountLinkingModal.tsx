"use client";

import { useState } from "react";
import { X, Link2, AlertCircle, CheckCircle2, Eye, EyeOff } from "lucide-react";

interface AccountLinkingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLink: (config: {
    api_key: string;
    secret_key: string;
    account_type: "paper" | "live";
  }) => Promise<void>;
}

export function AccountLinkingModal({
  isOpen,
  onClose,
  onLink,
}: AccountLinkingModalProps) {
  const [apiKey, setApiKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [accountType, setAccountType] = useState<"paper" | "live">("paper");
  const [showApiKey, setShowApiKey] = useState(false);
  const [showSecretKey, setShowSecretKey] = useState(false);
  const [isLinking, setIsLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    // Validation
    if (!apiKey.trim()) {
      setError("API Key is required");
      return;
    }
    if (!secretKey.trim()) {
      setError("Secret Key is required");
      return;
    }

    setIsLinking(true);

    try {
      await onLink({
        api_key: apiKey.trim(),
        secret_key: secretKey.trim(),
        account_type: accountType,
      });
      setSuccess(true);

      // Close modal after short delay
      setTimeout(() => {
        handleClose();
      }, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to link account");
    } finally {
      setIsLinking(false);
    }
  };

  const handleClose = () => {
    setApiKey("");
    setSecretKey("");
    setAccountType("paper");
    setShowApiKey(false);
    setShowSecretKey(false);
    setError(null);
    setSuccess(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0, 0, 0, 0.6)" }}
    >
      <div
        className="w-full max-w-md rounded-xl shadow-2xl mx-4"
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
              <Link2 size={20} style={{ color: "var(--accent-primary)" }} />
            </div>
            <div>
              <h2
                className="text-lg font-semibold"
                style={{ color: "var(--text-primary)" }}
              >
                Link Alpaca Account
              </h2>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Connect your trading account
              </p>
            </div>
          </div>
          <button
            onClick={handleClose}
            disabled={isLinking}
            className="p-2 rounded-lg transition-colors hover:bg-[var(--bg-secondary)]"
            style={{ color: "var(--text-muted)" }}
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6">
          {/* Account Type Selection */}
          <div className="mb-5">
            <label
              className="mb-2 block text-sm font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              Account Type
            </label>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setAccountType("paper")}
                className="flex-1 p-3 rounded-lg border-2 transition-all"
                style={{
                  borderColor:
                    accountType === "paper"
                      ? "var(--accent-primary)"
                      : "var(--border-color)",
                  background:
                    accountType === "paper"
                      ? "rgba(59, 130, 246, 0.1)"
                      : "transparent",
                }}
              >
                <div
                  className="font-medium"
                  style={{
                    color:
                      accountType === "paper"
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
                  Simulated environment
                </div>
              </button>
              <button
                type="button"
                onClick={() => setAccountType("live")}
                className="flex-1 p-3 rounded-lg border-2 transition-all"
                style={{
                  borderColor:
                    accountType === "live"
                      ? "var(--accent-danger)"
                      : "var(--border-color)",
                  background:
                    accountType === "live"
                      ? "rgba(239, 68, 68, 0.1)"
                      : "transparent",
                }}
              >
                <div
                  className="font-medium"
                  style={{
                    color:
                      accountType === "live"
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
                  Real money
                </div>
              </button>
            </div>
          </div>

          {/* API Key */}
          <div className="mb-4">
            <label
              className="mb-2 block text-sm font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              API Key
            </label>
            <div className="relative">
              <input
                type={showApiKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                disabled={isLinking}
                className="w-full rounded-lg border p-2.5 pr-10 text-sm"
                style={{
                  borderColor: "var(--border-color)",
                  background: "var(--bg-secondary)",
                  color: "var(--text-primary)",
                }}
                placeholder="Enter your Alpaca API key"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded hover:bg-[var(--bg-tertiary)]"
                style={{ color: "var(--text-muted)" }}
              >
                {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* Secret Key */}
          <div className="mb-5">
            <label
              className="mb-2 block text-sm font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              Secret Key
            </label>
            <div className="relative">
              <input
                type={showSecretKey ? "text" : "password"}
                value={secretKey}
                onChange={(e) => setSecretKey(e.target.value)}
                disabled={isLinking}
                className="w-full rounded-lg border p-2.5 pr-10 text-sm"
                style={{
                  borderColor: "var(--border-color)",
                  background: "var(--bg-secondary)",
                  color: "var(--text-primary)",
                }}
                placeholder="Enter your Alpaca secret key"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowSecretKey(!showSecretKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded hover:bg-[var(--bg-tertiary)]"
                style={{ color: "var(--text-muted)" }}
              >
                {showSecretKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* Info Box */}
          <div
            className="mb-5 rounded-lg border p-3"
            style={{
              borderColor: "var(--border-color)",
              background: "var(--bg-secondary)",
            }}
          >
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Get your API credentials from{" "}
              <a
                href="https://app.alpaca.markets/paper/dashboard/overview"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "var(--accent-primary)" }}
                className="underline"
              >
                Alpaca Dashboard
              </a>
              . Your credentials are encrypted and stored securely.
            </p>
          </div>

          {/* Error Message */}
          {error && (
            <div
              className="mb-4 rounded-lg border p-3 flex items-start gap-2"
              style={{
                borderColor: "var(--accent-danger)",
                background: "rgba(239, 68, 68, 0.1)",
              }}
            >
              <AlertCircle
                size={16}
                className="flex-shrink-0 mt-0.5"
                style={{ color: "var(--accent-danger)" }}
              />
              <p className="text-sm" style={{ color: "var(--accent-danger)" }}>
                {error}
              </p>
            </div>
          )}

          {/* Success Message */}
          {success && (
            <div
              className="mb-4 rounded-lg border p-3 flex items-start gap-2"
              style={{
                borderColor: "var(--accent-success)",
                background: "rgba(34, 197, 94, 0.1)",
              }}
            >
              <CheckCircle2
                size={16}
                className="flex-shrink-0 mt-0.5"
                style={{ color: "var(--accent-success)" }}
              />
              <p className="text-sm" style={{ color: "var(--accent-success)" }}>
                Account linked successfully!
              </p>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={handleClose}
              disabled={isLinking}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              style={{
                border: "1px solid var(--border-color)",
                color: "var(--text-secondary)",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLinking || success}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
              style={{
                background:
                  isLinking || success
                    ? "var(--bg-tertiary)"
                    : "var(--accent-primary)",
                color:
                  isLinking || success
                    ? "var(--text-muted)"
                    : "var(--bg-primary)",
                opacity: isLinking || success ? 0.6 : 1,
              }}
            >
              <Link2 size={16} />
              {isLinking ? "Linking..." : success ? "Linked!" : "Link Account"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
