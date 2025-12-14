/**
 * CrosshairSync - Synchronizes crosshair position across multiple chart panels
 *
 * When the crosshair moves in one chart, it broadcasts the position to all
 * other registered charts so they can update their crosshair to the same time.
 */

import type { Time, LogicalRange } from "lightweight-charts";
import type { CrosshairData, CrosshairMoveCallback } from "../BaseChartPanel";

export interface SyncablePanel {
  getPanelId: () => string;
  syncCrosshair: (data: CrosshairData) => void;
  clearCrosshair: () => void;
  setOnCrosshairMove: (callback: CrosshairMoveCallback) => void;
}

export class CrosshairSync {
  private panels: Map<string, SyncablePanel> = new Map();
  private lastCrosshairData: CrosshairData | null = null;
  private isEnabled: boolean = true;

  /**
   * Register a panel for crosshair synchronization
   */
  registerPanel(panel: SyncablePanel): void {
    const panelId = panel.getPanelId();
    this.panels.set(panelId, panel);

    // Setup the crosshair move callback for this panel
    panel.setOnCrosshairMove((data: CrosshairData, sourcePanel: string) => {
      this.handleCrosshairMove(data, sourcePanel);
    });
  }

  /**
   * Unregister a panel from crosshair synchronization
   */
  unregisterPanel(panelId: string): void {
    this.panels.delete(panelId);
  }

  /**
   * Handle crosshair move from a source panel - broadcast to all other panels
   */
  private handleCrosshairMove(data: CrosshairData, sourcePanel: string): void {
    if (!this.isEnabled) return;

    this.lastCrosshairData = data;

    // #region agent log
    fetch("http://127.0.0.1:7242/ingest/3d78da6f-49c7-481a-bafb-b1cb31305326", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        location: "CrosshairSync.ts:handleCrosshairMove",
        message: "Crosshair move",
        data: {
          sourcePanel,
          time: data.time,
          price: data.price,
          registeredPanels: Array.from(this.panels.keys()),
        },
        timestamp: Date.now(),
        sessionId: "debug-session",
        hypothesisId: "H50",
      }),
    }).catch(() => {});
    // #endregion

    // Broadcast to all panels except the source
    for (const [panelId, panel] of this.panels) {
      if (panelId !== sourcePanel) {
        if (data.time) {
          panel.syncCrosshair(data);
        } else {
          panel.clearCrosshair();
        }
      }
    }
  }

  /**
   * Manually set crosshair position on all panels
   */
  setCrosshairPosition(data: CrosshairData): void {
    this.lastCrosshairData = data;

    for (const panel of this.panels.values()) {
      if (data.time) {
        panel.syncCrosshair(data);
      } else {
        panel.clearCrosshair();
      }
    }
  }

  /**
   * Sync crosshair to all panels EXCEPT the source panel
   * This preserves the source panel's native free-moving crosshair behavior
   */
  syncCrosshairExcept(data: CrosshairData, sourcePanel: string): void {
    this.lastCrosshairData = data;

    for (const [panelId, panel] of this.panels) {
      if (panelId !== sourcePanel) {
        if (data.time) {
          panel.syncCrosshair(data);
        } else {
          panel.clearCrosshair();
        }
      }
    }
  }

  /**
   * Clear crosshair on all panels
   */
  clearAllCrosshairs(): void {
    this.lastCrosshairData = null;

    for (const panel of this.panels.values()) {
      panel.clearCrosshair();
    }
  }

  /**
   * Get the last known crosshair data
   */
  getLastCrosshairData(): CrosshairData | null {
    return this.lastCrosshairData;
  }

  /**
   * Enable/disable crosshair synchronization
   */
  setEnabled(enabled: boolean): void {
    this.isEnabled = enabled;
  }

  /**
   * Check if sync is enabled
   */
  isActive(): boolean {
    return this.isEnabled;
  }

  /**
   * Get list of registered panel IDs
   */
  getRegisteredPanels(): string[] {
    return Array.from(this.panels.keys());
  }

  /**
   * Cleanup - unregister all panels
   */
  cleanup(): void {
    this.panels.clear();
    this.lastCrosshairData = null;
  }
}

export default CrosshairSync;
