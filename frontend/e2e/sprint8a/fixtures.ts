/**
 * Sprint 8A Playwright fixtures — SavedViews + WalixAIBar CRUD.
 *
 * Re-exports everything from Sprint 7 and extends with Sprint 8A helpers.
 *
 * Usage:
 *   import { test, expect } from "./fixtures";
 *
 *   test("can save a view", async ({ authedPage, savedView }) => { ... });
 */

import { test as base, expect } from "@playwright/test";

// ── Re-export Sprint 7 fixtures ───────────────────────────────────────────────

export {
  loginAs,
  injectToken,
  createTestContact,
  type TestContact,
  type UserRole,
} from "../sprint7/fixtures";

export { expect };

// ── Sprint 7 base test (authedPage, testContact, ownerToken) ──────────────────

import { test as sprint7Test } from "../sprint7/fixtures";

// ── Config ────────────────────────────────────────────────────────────────────

const API_URL = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000";

// ── Saved view API helpers ────────────────────────────────────────────────────

export interface TestSavedView {
  id: string;
  user_id: string;
  tenant_id: string;
  name: string;
  filters: Record<string, unknown>;
  view_mode: "list" | "kanban" | "cards";
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export async function createSavedView(
  token: string,
  overrides: Partial<{
    name: string;
    filters: Record<string, unknown>;
    viewMode: "list" | "kanban" | "cards";
    isDefault: boolean;
  }> = {}
): Promise<TestSavedView> {
  const body = {
    name: overrides.name ?? `Vista E2E ${Date.now()}`,
    filters: overrides.filters ?? {},
    view_mode: overrides.viewMode ?? "list",
    is_default: overrides.isDefault ?? false,
  };

  const res = await fetch(`${API_URL}/api/v1/contacts/views`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`createSavedView failed ${res.status}: ${text}`);
  }

  return res.json();
}

export async function deleteSavedView(token: string, viewId: string): Promise<void> {
  await fetch(`${API_URL}/api/v1/contacts/views/${viewId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => undefined);
}

export async function getSavedViews(token: string): Promise<TestSavedView[]> {
  const res = await fetch(`${API_URL}/api/v1/contacts/views`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  return res.json();
}

export async function setDefaultView(
  token: string,
  viewId: string
): Promise<TestSavedView> {
  const res = await fetch(`${API_URL}/api/v1/contacts/views/${viewId}/set-default`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`setDefaultView failed ${res.status}: ${text}`);
  }
  return res.json();
}

// ── AIBar command helper ───────────────────────────────────────────────────────

export async function sendAIBarCommand(
  token: string,
  message: string,
  context: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_URL}/api/ai/command`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, context, history: [] }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`sendAIBarCommand failed ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Extended fixtures ─────────────────────────────────────────────────────────

type Sprint8AFixtures = {
  /** A saved view created via API before the test runs. */
  savedView: TestSavedView;
  /** Default saved view (is_default = true). */
  defaultView: TestSavedView;
  /** 10 saved views — exercises the Starter plan limit. */
  tenSavedViews: TestSavedView[];
};

export const test = sprint7Test.extend<Sprint8AFixtures>({
  savedView: async ({ ownerToken }, use) => {
    const view = await createSavedView(ownerToken, {
      name: `Vista E2E ${Date.now()}`,
      filters: { status: ["nuevo"] },
      viewMode: "list",
      isDefault: false,
    });
    await use(view);
    await deleteSavedView(ownerToken, view.id);
  },

  defaultView: async ({ ownerToken }, use) => {
    const view = await createSavedView(ownerToken, {
      name: `Vista Default E2E ${Date.now()}`,
      filters: {},
      viewMode: "kanban",
      isDefault: true,
    });
    await use(view);
    await deleteSavedView(ownerToken, view.id);
  },

  tenSavedViews: async ({ ownerToken }, use) => {
    const views: TestSavedView[] = [];
    for (let i = 1; i <= 10; i++) {
      const v = await createSavedView(ownerToken, {
        name: `Vista Límite ${i}`,
        filters: {},
        viewMode: "list",
        isDefault: i === 1,
      });
      views.push(v);
    }
    await use(views);
    await Promise.all(views.map((v) => deleteSavedView(ownerToken, v.id)));
  },
});
