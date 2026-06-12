/**
 * P-09 — Playwright E2E: página /contacts
 *
 * Cubre: carga de lista, toggle de vistas, filtros, búsqueda,
 * selección múltiple, barra de acciones masivas, sheet de creación.
 *
 * Requiere servidor frontend + backend corriendo (ver fixtures.ts).
 */

import { test, expect, createTestContact } from "./fixtures";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173";

test.describe("Página /contacts", () => {
  test.beforeEach(async ({ authedPage }) => {
    await authedPage.goto(`${BASE_URL}/contacts`);
    await expect(authedPage.getByRole("heading", { name: "Contactos" })).toBeVisible();
  });

  // ── Vista lista ────────────────────────────────────────────────────────────

  test("la tabla de lista se muestra con columna Contacto", async ({ authedPage: page }) => {
    await expect(page.getByTestId("contacts-table")).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Contacto" })).toBeVisible();
  });

  // ── Toggle de vistas ───────────────────────────────────────────────────────

  test("cambiar a vista Kanban muestra las 5 columnas de estado", async ({ authedPage: page }) => {
    await page.getByTestId("view-toggle-kanban").click();
    for (const col of ["nuevo", "en_calificacion", "calificado", "escalado", "perdido"]) {
      await expect(page.getByTestId(`kanban-column-${col}`)).toBeVisible();
    }
  });

  test("cambiar a vista Tarjetas oculta la tabla", async ({ authedPage: page }) => {
    await page.getByTestId("view-toggle-cards").click();
    await expect(page.getByTestId("contacts-table")).not.toBeVisible();
  });

  test("volver a vista Lista restaura la tabla", async ({ authedPage: page }) => {
    await page.getByTestId("view-toggle-kanban").click();
    await page.getByTestId("view-toggle-list").click();
    await expect(page.getByTestId("contacts-table")).toBeVisible();
  });

  test("la vista seleccionada se persiste en localStorage", async ({ authedPage: page }) => {
    await page.getByTestId("view-toggle-kanban").click();
    const stored = await page.evaluate(() => localStorage.getItem("walix-contacts-view"));
    expect(stored).toBe("kanban");

    await page.getByTestId("view-toggle-list").click();
    const stored2 = await page.evaluate(() => localStorage.getItem("walix-contacts-view"));
    expect(stored2).toBe("list");
  });

  // ── Filtros ────────────────────────────────────────────────────────────────

  test("abrir el panel de filtros y aplicar filtro por estado nuevo", async ({ authedPage: page }) => {
    await page.getByTestId("filters-toggle-btn").click();
    await expect(page.getByTestId("filters-panel")).toBeVisible();
    await page.getByTestId("status-filter-nuevo").click();
    await expect(page).toHaveURL(/status=nuevo/);
  });

  test("limpiar filtros elimina los parámetros de URL", async ({ authedPage: page }) => {
    await page.getByTestId("filters-toggle-btn").click();
    await page.getByTestId("status-filter-nuevo").click();
    await expect(page).toHaveURL(/status=nuevo/);

    await page.getByTestId("clear-filters-btn").click();
    await expect(page).not.toHaveURL(/status=nuevo/);
  });

  test("cerrar el panel de filtros lo oculta", async ({ authedPage: page }) => {
    await page.getByTestId("filters-toggle-btn").click();
    await expect(page.getByTestId("filters-panel")).toBeVisible();
    await page.getByTestId("filters-toggle-btn").click();
    await expect(page.getByTestId("filters-panel")).not.toBeVisible();
  });

  // ── Búsqueda ───────────────────────────────────────────────────────────────

  test("buscar por nombre actualiza el parámetro q en la URL", async ({ authedPage: page }) => {
    await page.getByTestId("contacts-search").fill("test");
    // Esperar debounce de 300 ms
    await page.waitForTimeout(400);
    await expect(page).toHaveURL(/q=test/);
  });

  test("limpiar la búsqueda quita el parámetro q", async ({ authedPage: page }) => {
    await page.getByTestId("contacts-search").fill("algo");
    await page.waitForTimeout(400);
    await page.getByTestId("contacts-search").clear();
    await page.waitForTimeout(400);
    await expect(page).not.toHaveURL(/q=/);
  });

  // ── Selección múltiple ─────────────────────────────────────────────────────

  test("seleccionar una fila muestra la barra de acciones masivas", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.waitForTimeout(500); // dar tiempo al query para cargar
    const rows = page.getByTestId("contact-row");
    await expect(rows.first()).toBeVisible();
    await rows.first().getByRole("checkbox").click();
    await expect(page.getByTestId("bulk-actions-bar")).toBeVisible();
    // Cleanup
    void testContact; // fixture garantiza al menos 1 contacto
  });

  test("deseleccionar la fila oculta la barra de acciones masivas", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.waitForTimeout(500);
    const rows = page.getByTestId("contact-row");
    await expect(rows.first()).toBeVisible();
    const cb = rows.first().getByRole("checkbox");
    await cb.click();
    await expect(page.getByTestId("bulk-actions-bar")).toBeVisible();
    await cb.click();
    await expect(page.getByTestId("bulk-actions-bar")).not.toBeVisible();
    void testContact;
  });

  test("checkbox de cabecera selecciona todas las filas visibles", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.waitForTimeout(500);
    await expect(page.getByTestId("contact-row").first()).toBeVisible();
    await page.getByRole("checkbox", { name: "Seleccionar todos" }).click();
    await expect(page.getByTestId("bulk-actions-bar")).toBeVisible();
    void testContact;
  });

  // ── WhatsApp masivo deshabilitado ──────────────────────────────────────────

  test("el botón de WhatsApp masivo está deshabilitado y muestra tooltip de Sprint 8", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.waitForTimeout(500);
    const rows = page.getByTestId("contact-row");
    await expect(rows.first()).toBeVisible();
    await rows.first().getByRole("checkbox").click();
    await expect(page.getByTestId("bulk-wa-btn")).toBeDisabled();
    await page.getByTestId("bulk-wa-btn").hover();
    await expect(page.getByText(/Sprint 8/)).toBeVisible();
    void testContact;
  });

  // ── Sheet de nuevo contacto ────────────────────────────────────────────────

  test("abrir el sheet de nuevo contacto muestra el título", async ({ authedPage: page }) => {
    await page.getByTestId("new-contact-btn").click();
    await expect(page.getByRole("heading", { name: "Nuevo contacto" })).toBeVisible();
  });

  test("cancelar el sheet lo cierra sin crear contacto", async ({ authedPage: page }) => {
    await page.getByTestId("new-contact-btn").click();
    await expect(page.getByRole("heading", { name: "Nuevo contacto" })).toBeVisible();
    await page.getByRole("button", { name: "Cancelar" }).click();
    await expect(page.getByRole("heading", { name: "Nuevo contacto" })).not.toBeVisible();
  });

  test("crear contacto con todos los campos cierra el sheet", async ({ authedPage: page }) => {
    const phone = `+52155${Date.now().toString().slice(-7)}`;
    await page.getByTestId("new-contact-btn").click();
    await page.getByPlaceholder("+521234567890").fill(phone);
    await page.getByPlaceholder("Juan").fill("Nuevo");
    await page.getByPlaceholder("García").fill("PW Test");
    await page.getByPlaceholder("ACME S.A.").fill("E2E Corp");
    await page.getByRole("button", { name: "Crear contacto" }).click();
    await expect(
      page.getByRole("heading", { name: "Nuevo contacto" }),
    ).not.toBeVisible({ timeout: 8_000 });
  });

  test("enviar el formulario sin teléfono no cierra el sheet", async ({ authedPage: page }) => {
    await page.getByTestId("new-contact-btn").click();
    await page.getByPlaceholder("Juan").fill("Sin Teléfono");
    await page.getByRole("button", { name: "Crear contacto" }).click();
    // phone es required — el sheet debe permanecer abierto
    await expect(page.getByRole("heading", { name: "Nuevo contacto" })).toBeVisible();
  });

  // ── Búsqueda con contacto real ─────────────────────────────────────────────

  test("buscar por nombre del contacto creado lo muestra en la tabla", async ({
    authedPage: page,
    ownerToken,
  }) => {
    const uniqueName = `PW${Date.now()}`;
    await createTestContact(ownerToken, { name: uniqueName });

    await page.getByTestId("contacts-search").fill(uniqueName);
    await page.waitForTimeout(500);
    await expect(page.getByTestId("contact-row").first()).toContainText(uniqueName, {
      timeout: 8_000,
    });
  });
});
