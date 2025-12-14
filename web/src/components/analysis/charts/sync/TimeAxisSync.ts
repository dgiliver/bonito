/**
 * TimeAxisSync - Synchronizes time axis (zoom/pan) across multiple chart panels
 *
 * When the visible time range changes in one chart (due to zoom/pan),
 * it broadcasts to all other registered charts so they stay synchronized.
 */

import type { LogicalRange } from "lightweight-charts";
import type { TimeRangeChangeCallback } from "../BaseChartPanel";

export interface TimeAxisSyncablePanel {
  getPanelId: () => string;
  syncTimeRange: (range: LogicalRange | null) => void;
  getVisibleTimeRange: () => LogicalRange | null;
  setOnTimeRangeChange: (callback: TimeRangeChangeCallback) => void;
  fitContent: () => void;
}

export class TimeAxisSync {
  private panels: Map<string, TimeAxisSyncablePanel> = new Map();
  private lastTimeRange: LogicalRange | null = null;
  private isEnabled: boolean = true;
  private isSyncing: boolean = false;

  /**
   * Register a panel for time axis synchronization
   */
  registerPanel(panel: TimeAxisSyncablePanel): void {
    const panelId = panel.getPanelId();
    this.panels.set(panelId, panel);

    // Setup the time range change callback for this panel
    panel.setOnTimeRangeChange(
      (range: LogicalRange | null, sourcePanel: string) => {
        this.handleTimeRangeChange(range, sourcePanel);
      },
    );

    // If we have a saved time range, apply it to the new panel
    if (this.lastTimeRange) {
      panel.syncTimeRange(this.lastTimeRange);
    }
  }

  /**
   * Unregister a panel from time axis synchronization
   */
  unregisterPanel(panelId: string): void {
    this.panels.delete(panelId);
  }

  /**
   * Handle time range change from a source panel - broadcast to all other panels
   */
  private handleTimeRangeChange(
    range: LogicalRange | null,
    sourcePanel: string,
  ): void {
    if (!this.isEnabled || this.isSyncing) return;
    if (!range) return;

    this.lastTimeRange = range;
    this.isSyncing = true;

    try {
      // Broadcast to all panels except the source
      for (const [panelId, panel] of this.panels) {
        if (panelId !== sourcePanel) {
          panel.syncTimeRange(range);
        }
      }
    } finally {
      // Reset the syncing flag after a small delay to allow for the sync to complete
      setTimeout(() => {
        this.isSyncing = false;
      }, 10);
    }
  }

  /**
   * Manually set time range on all panels
   */
  setTimeRange(range: LogicalRange | null): void {
    if (!range) return;

    this.lastTimeRange = range;
    this.isSyncing = true;

    try {
      for (const panel of this.panels.values()) {
        panel.syncTimeRange(range);
      }
    } finally {
      setTimeout(() => {
        this.isSyncing = false;
      }, 10);
    }
  }

  /**
   * Fit content on all panels
   */
  fitAllContent(): void {
    for (const panel of this.panels.values()) {
      panel.fitContent();
    }
  }

  /**
   * Get the last known time range
   */
  getLastTimeRange(): LogicalRange | null {
    return this.lastTimeRange;
  }

  /**
   * Get the current visible time range from the primary (first) panel
   */
  getCurrentTimeRange(): LogicalRange | null {
    const firstPanel = this.panels.values().next().value;
    if (firstPanel) {
      return firstPanel.getVisibleTimeRange();
    }
    return this.lastTimeRange;
  }

  /**
   * Enable/disable time axis synchronization
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
    this.lastTimeRange = null;
    this.isSyncing = false;
  }
}

export default TimeAxisSync;
