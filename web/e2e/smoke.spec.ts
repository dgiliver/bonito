import { test, expect } from "@playwright/test";

/**
 * Minimal smoke scaffold — see tasks/phase2_coordination.md P2-8 / Decision #10.
 *
 * Scope is deliberately narrow: two real, already-rendered, backend-free paths.
 * Not a full E2E suite — a proof that the harness itself works end-to-end against
 * the real dev server.
 */

test.describe("chart rendering", () => {
  test("chart view renders the chart canvas", async ({ page }) => {
    await page.goto("/");

    // Default view is "analysis", not "chart" — navigate via the sidebar nav
    // button (no data-testid on Sidebar; accessible name is the only stable hook).
    await page.getByRole("button", { name: "Chart" }).click();

    // AdvancedChart is loaded via next/dynamic with ssr: false, so the
    // chart-canvas container only appears once the client chunk has hydrated.
    // Generous timeout to absorb that dynamic-import + chart-library init.
    await expect(page.getByTestId("chart-canvas")).toBeVisible({
      timeout: 30_000,
    });
  });
});

test.describe("chat empty state", () => {
  test("agent view shows the empty state before any messages are sent", async ({
    page,
  }) => {
    await page.goto("/");

    // Navigate to the "Agent" (chat-only) view via the sidebar.
    await page.getByRole("button", { name: "Agent" }).click();

    // NOTE: Chat.tsx renders its own inline empty-state JSX (Bot icon +
    // heading + suggestion buttons) — it does NOT use VirtualizedMessageList,
    // which carries data-testid="empty-state"/"message-list" but has zero
    // production importers (confirmed by repo-wide grep; only its own
    // colocated unit test renders it). Asserting on the heading text is the
    // faithful, reachable equivalent of "chat empty state" today.
    await expect(
      page.getByRole("heading", { name: "How can I help you today?" }),
    ).toBeVisible({ timeout: 30_000 });
  });
});
