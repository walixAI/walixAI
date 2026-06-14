/**
 * P-09 — Playwright E2E: nota rápida desde lista de contactos (Sprint 8A)
 *
 * Cubre: visibilidad del trigger en hover, apertura del popover, guardar nota
 * con toast de éxito, cierre con Escape sin texto y cierre con confirmación
 * cuando hay texto escrito.
 *
 * Adaptaciones al spec original:
 *   - `page.goto('/contacts')` funciona via baseURL en playwright.config.ts
 *   - Se espera que al menos un contacto exista en la DB del tenant del asesor
 *   - El popover usa `onEscapeKeyDown={(e) => e.preventDefault()}` para que
 *     Radix no cierre el popover antes de que `requestClose()` evalúe el texto
 *
 * Prerrequisitos:
 *   - Frontend: npm run dev (puerto 3000)
 *   - Backend: uvicorn app.main:app (puerto 8000)
 *   - Credenciales en env: TEST_ASESOR_EMAIL, TEST_ASESOR_PASSWORD
 *     (default: asesor@walix.test / test1234)
 */

import { test, expect } from "@playwright/test";
import { loginAs } from "./fixtures";

// ── P-09-01 ───────────────────────────────────────────────────────────────────

test("ícono de nota rápida aparece al hacer hover en fila", async ({ page }) => {
  await loginAs(page, "asesor");
  await page.goto("/contacts");

  const firstRow = page.locator('[data-testid="contact-row"]').first();
  await expect(firstRow).toBeVisible({ timeout: 10_000 });
  await firstRow.hover();

  await expect(
    firstRow.locator('[data-testid="quick-note-trigger"]')
  ).toBeVisible();
});

// ── P-09-02 ───────────────────────────────────────────────────────────────────

test("abrir popover de nota rápida muestra textarea", async ({ page }) => {
  await loginAs(page, "asesor");
  await page.goto("/contacts");

  const firstRow = page.locator('[data-testid="contact-row"]').first();
  await expect(firstRow).toBeVisible({ timeout: 10_000 });
  await firstRow.hover();
  await firstRow.locator('[data-testid="quick-note-trigger"]').click();

  await expect(page.getByPlaceholder(/escribe una nota/i)).toBeVisible();
  await expect(
    page.getByRole("button", { name: /guardar nota/i })
  ).toBeDisabled();
});

// ── P-09-03 ───────────────────────────────────────────────────────────────────

test("guardar nota crea activity y muestra toast", async ({ page }) => {
  await loginAs(page, "asesor");
  await page.goto("/contacts");

  const firstRow = page.locator('[data-testid="contact-row"]').first();
  await expect(firstRow).toBeVisible({ timeout: 10_000 });
  await firstRow.hover();
  await firstRow.locator('[data-testid="quick-note-trigger"]').click();

  await page.getByPlaceholder(/escribe una nota/i).fill("Nota de prueba e2e");
  await page.getByRole("button", { name: /guardar nota/i }).click();

  // Toast de éxito (optimista — aparece antes de que el servidor responda)
  await expect(page.getByText(/nota guardada/i)).toBeVisible({ timeout: 5_000 });
  // El popover se cierra al confirmar la mutación
  await expect(page.getByPlaceholder(/escribe una nota/i)).not.toBeVisible({
    timeout: 8_000,
  });
});

// ── P-09-04 ───────────────────────────────────────────────────────────────────

test("escape cierra popover sin texto escrito sin confirmación", async ({
  page,
}) => {
  await loginAs(page, "asesor");
  await page.goto("/contacts");

  const firstRow = page.locator('[data-testid="contact-row"]').first();
  await expect(firstRow).toBeVisible({ timeout: 10_000 });
  await firstRow.hover();
  await firstRow.locator('[data-testid="quick-note-trigger"]').click();

  await expect(page.getByPlaceholder(/escribe una nota/i)).toBeVisible();
  await page.keyboard.press("Escape");

  await expect(
    page.getByPlaceholder(/escribe una nota/i)
  ).not.toBeVisible({ timeout: 2_000 });
});

// ── P-09-05 ───────────────────────────────────────────────────────────────────

test("escape con texto escrito muestra confirmación", async ({ page }) => {
  await loginAs(page, "asesor");
  await page.goto("/contacts");

  const firstRow = page.locator('[data-testid="contact-row"]').first();
  await expect(firstRow).toBeVisible({ timeout: 10_000 });
  await firstRow.hover();
  await firstRow.locator('[data-testid="quick-note-trigger"]').click();

  await page.getByPlaceholder(/escribe una nota/i).fill("Texto sin guardar");
  await page.keyboard.press("Escape");

  await expect(page.getByText(/¿descartar nota/i)).toBeVisible({
    timeout: 2_000,
  });
});
