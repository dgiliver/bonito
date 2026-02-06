"use client";

import { useState } from "react";

interface RiskWarningModalProps {
  isOpen: boolean;
  riskScore: "low" | "medium" | "high" | "extreme";
  warnings: string[];
  onAccept: () => void;
  onCancel: () => void;
}

export function RiskWarningModal({
  isOpen,
  riskScore,
  warnings,
  onAccept,
  onCancel,
}: RiskWarningModalProps) {
  const [acknowledged, setAcknowledged] = useState(false);

  if (!isOpen) return null;

  const riskColors = {
    low: "text-green-600",
    medium: "text-yellow-600",
    high: "text-orange-600",
    extreme: "text-red-600",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-gray-900">
          High Risk Configuration Detected
        </h2>

        <div className="mt-4">
          <p className="text-sm text-gray-600">
            Risk Score:{" "}
            <span className={`font-semibold ${riskColors[riskScore]}`}>
              {riskScore.toUpperCase()}
            </span>
          </p>

          <div className="mt-4 rounded bg-gray-50 p-3">
            <p className="text-sm font-medium text-gray-700">Warnings:</p>
            <ul className="mt-2 space-y-1">
              {warnings.map((warning, i) => (
                <li key={i} className="text-sm text-gray-600">
                  {warning}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-4">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              className="rounded border-gray-300"
            />
            <span className="text-sm text-gray-700">
              I understand these risks and want to proceed anyway
            </span>
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
          >
            Go Back
          </button>
          <button
            onClick={onAccept}
            disabled={!acknowledged}
            className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Deploy Anyway
          </button>
        </div>
      </div>
    </div>
  );
}
