/**
 * Sprint 7 Playwright fixtures — contacts module.
 *
 * Setup:
 *   npm install -D @playwright/test
 *   npx playwright install chromium
 *
 * Usage:
 *   import { test, expect } from "./fixtures";
 *
 *   test("contacts list loads", async ({ page, authedPage }) => {
 *     await authedPage.goto("/contacts");
 *     await expect(page.getByRole("heading", { name: "Contactos" })).toBeVisible();
 *   });
 */

import { test as base, type Page, type BrowserContext } from "@playwright/test";

// ── Config ────────────────────────────────────────────────────────────────────

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173";
const API_URL = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000";

// Seeded test credentials — must match the DB seed or conftest fixtures
const TEST_USERS = {
  owner: {
    email: process.env.TEST_OWNER_EMAIL ?? "owner@walix.test",
    password: process.env.TEST_OWNER_PASSWORD ?? "test1234",
    role: "owner" as const,
  },
  manager: {
    email: process.env.TEST_MANAGER_EMAIL ?? "manager@walix.test",
    password: process.env.TEST_MANAGER_PASSWORD ?? "test1234",
    role: "manager" as const,
  },
  asesor: {
    email: process.env.TEST_ASESOR_EMAIL ?? "asesor@walix.test",
    password: process.env.TEST_ASESOR_PASSWORD ?? "test1234",
    role: "asesor" as const,
  },
} as const;

export type UserRole = keyof typeof TEST_USERS;

// ── Login helper ──────────────────────────────────────────────────────────────

/**
 * Logs in as the given role via the UI login form.
 * Waits until the dashboard route is reached before returning.
 */
export async function loginAs(page: Page, role: UserRole): Promise<void> {
  const { email, password } = TEST_USERS[role];

  await page.goto(`${BASE_URL}/login`);
  await page.getByLabel(/correo|email/i).fill(email);
  await page.getByLabel(/contraseña|password/i).fill(password);
  await page.getByRole("button", { name: /iniciar sesión|entrar|login/i }).click();
  await page.waitForURL(/\/(dashboard|contacts|whatsapp)/, { timeout: 10_000 });
}

/**
 * Injects a JWT token directly into localStorage — skips the login form.
 * Use when you need auth state but don't want to test the login flow.
 */
export async function injectToken(context: BrowserContext, token: string): Promise<void> {
  await context.addInitScript((jwt) => {
    localStorage.setItem("walix_token", jwt);
  }, token);
}

// ── API helpers ───────────────────────────────────────────────────────────────

export interface TestContact {
  id: string;
  wa_phone: string;
  name: string;
  last_name: string | null;
  status: string;
}

/**
 * Creates a contact via the API and returns the created record.
 * Requires a valid Bearer token.
 */
export async function createTestContact(
  token: string,
  overrides: Partial<{
    phone: string;
    name: string;
    lastName: string;
    company: string;
    prospectionSource: string;
  }> = {}
): Promise<TestContact> {
  const body = {
    phone: overrides.phone ?? "+5215512340001",
    name: overrides.name ?? "Contacto E2E",
    lastName: overrides.lastName ?? "Playwright",
    company: overrides.company ?? "Test Corp",
    prospectionSource: overrides.prospectionSource ?? "manual",
  };

  const res = await fetch(`${API_URL}/api/v1/contacts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`createTestContact failed ${res.status}: ${text}`);
  }

  return res.json();
}

// ── Custom fixtures ───────────────────────────────────────────────────────────

type WalixFixtures = {
  /** Page already logged in as owner. */
  authedPage: Page;
  /** A contact created via API before the test runs (owner auth). */
  testContact: TestContact;
  /** The owner Bearer token (obtained via login). */
  ownerToken: string;
};

export const test = base.extend<WalixFixtures>({
  authedPage: async ({ page }, use) => {
    await loginAs(page, "owner");
    await use(page);
  },

  ownerToken: async ({ page }, use) => {
    await loginAs(page, "owner");
    // Read the token that the app stored after a successful login
    const token = await page.evaluate(
      () =>
        localStorage.getItem("walix_token") ??
        sessionStorage.getItem("walix_token") ??
        ""
    );
    await use(token);
  },

  testContact: async ({ ownerToken }, use) => {
    const contact = await createTestContact(ownerToken, {
      phone: `+52155${Date.now().toString().slice(-7)}`,
      name: "Test E2E",
      lastName: "Playwright",
    });
    await use(contact);
    // Cleanup — best-effort; test DB rollback handles it in CI
    await fetch(`${API_URL}/api/v1/contacts/${contact.id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${ownerToken}` },
    }).catch(() => undefined);
  },
});

export { expect } from "@playwright/test";
