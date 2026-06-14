/**
 * P-10 — Playwright E2E: tooltip de última actividad en lista de contactos (Sprint 8A)
 *
 * Cubre: columna última actividad visible, tooltip al hacer hover (con resumen
 * completo o fecha exacta), y estado vacío "Sin actividades registradas".
 *
 * Adaptaciones al spec original:
 *   - El texto vacío del tooltip es "Sin actividades registradas" (no "Sin actividad")
 *     → el regex /sin actividad/i cubre ambas variantes
 *   - Radix Tooltip tiene delayDuration={300} → timeout de 2 000 ms es suficiente
 *   - `data-testid="last-activity-col"` está en el <TableHead> (header de columna)
 *   - `data-testid="last-activity-cell"` está en el span trigger de cada fila
 *   - `data-empty="true"` se asigna cuando lastActivitySummary y lastActivityAt son null
 *
 * Prerrequisitos:
 *   - Frontend: npm run dev (puerto 3000)
 *   - Backend: uvicorn app.main:app (puerto 8000)
 *   - Credenciales en env: TEST_ASESOR_EMAIL, TEST_ASESOR_PASSWORD
 */

import { test, expect } from "@playwright/test";
import { loginAs } from "./fixtures";

// ── P-10-01 ───────────────────────────────────────────────────────────────────

test("columna última actividad muestra tiempo relativo", async ({ page }) => {
  await loginAs(page, "asesor");
  await page.goto("/contacts");

  // El header de la columna debe ser visible
  await expect(page.getByTestId("last-activity-col").first()).toBeVisible({
    timeout: 10_000,
  });

  // Al menos una celda de la columna debe mostrar texto relativo (Hoy, Ayer, hace Nd…)
  const firstCell = page.getByTestId("last-activity-cell").first();
  await expect(firstCell).toBeVisible({ timeout: 10_000 });
  await expect(firstCell).not.toBeEmpty();
});

// ── P-10-02 ───────────────────────────────────────────────────────────────────

test("hover en última actividad muestra tooltip con resumen completo", async ({
  page,
}) => {
  await loginAs(page, "asesor");
  await page.goto("/contacts");

  // Buscar la primera celda que NO esté vacía (tiene actividad)
  const cells = page.getByTestId("last-activity-cell");
  await expect(cells.first()).toBeVisible({ timeout: 10_000 });

  // Preferimos una celda con actividad; si todas están vacías tomamos la primera
  const cellWithActivity = cells.filter({ hasNot: page.locator('[data-empty="true"]') }).first();
  const fallback = cells.first();
  const activityCell = (await cellWithActivity.count()) > 0 ? cellWithActivity : fallback;

  await activityCell.hover();

  // El tooltip debe aparecer (Radix usa role="tooltip" en TooltipContent)
  const tooltip = page.locator('[role="tooltip"]');
  await expect(tooltip).toBeVisible({ timeout: 2_000 });

  // El tooltip debe tener contenido no vacío
  await expect(tooltip).not.toBeEmpty();
});

// ── P-10-03 ───────────────────────────────────────────────────────────────────

test("contacto sin actividad muestra estado vacío en tooltip", async ({
  page,
}) => {
  await loginAs(page, "asesor");
  await page.goto("/contacts");

  await expect(
    page.getByTestId("last-activity-cell").first()
  ).toBeVisible({ timeout: 10_000 });

  // Buscar celdas marcadas como vacías
  const emptyCells = page.locator(
    '[data-testid="last-activity-cell"][data-empty="true"]'
  );
  const count = await emptyCells.count();

  if (count === 0) {
    // No hay contactos sin actividad en el dataset de prueba
    test.skip();
    return;
  }

  await emptyCells.first().hover();

  // El tooltip muestra "Sin actividades registradas"
  await expect(page.locator('[role="tooltip"]')).toContainText(
    /sin actividad/i,
    { timeout: 2_000 }
  );
});
