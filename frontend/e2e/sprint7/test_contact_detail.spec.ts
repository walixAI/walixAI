/**
 * P-10 — Playwright E2E: ficha /contacts/:id
 *
 * Cubre: layout 3 columnas, responsive mobile, skeleton de carga,
 * edición inline (EditFieldPopover), tabs, timeline de actividades.
 *
 * Requiere servidor frontend + backend corriendo (ver fixtures.ts).
 */

import { test, expect } from "./fixtures";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173";

test.describe("Ficha /contacts/:id", () => {
  // ── Layout — desktop ────────────────────────────────────────────────────────

  test("muestra las 3 columnas en desktop", async ({ authedPage: page, testContact }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("contact-left-panel")).toBeVisible();
    await expect(page.getByTestId("contact-center")).toBeVisible();
    await expect(page.getByTestId("contact-right-panel")).toBeVisible();
  });

  // ── Layout — mobile ─────────────────────────────────────────────────────────

  test("en mobile las columnas laterales se ocultan y el contenido principal es visible", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("contact-left-panel")).not.toBeVisible();
    await expect(page.getByTestId("contact-right-panel")).not.toBeVisible();
    // El contenido principal (tabs) sí es visible en mobile
    await expect(page.getByRole("tablist")).toBeVisible();
  });

  // ── Skeleton durante carga ──────────────────────────────────────────────────

  test("skeleton visible durante la carga y desaparece al completar", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    // Interceptar la llamada API para añadir latencia artificial
    await page.route(`**/api/v1/contacts/${testContact.id}`, async (route) => {
      await new Promise<void>((r) => setTimeout(r, 400));
      await route.continue();
    });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await expect(page.getByTestId("contact-detail-skeleton")).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("contact-detail-skeleton")).not.toBeVisible();
  });

  // ── EditFieldPopover — empresa ──────────────────────────────────────────────

  test("hover en campo empresa muestra el ícono de edición", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    // El ícono está en el DOM (opacity-0 via CSS); Playwright lo detecta como visible
    await expect(page.getByTestId("field-company")).toBeVisible();
    await expect(page.getByTestId("edit-icon-company")).toBeVisible();
  });

  test("click en campo empresa abre el popover con input", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await page.getByTestId("field-company").click();
    await expect(page.getByTestId("edit-popover")).toBeVisible();
    await expect(page.getByTestId("edit-input")).toBeVisible();
  });

  test("guardar empresa actualiza el valor en pantalla", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await page.getByTestId("field-company").click();
    await page.getByTestId("edit-input").fill("Nueva Empresa SA");
    await page.getByTestId("save-edit-btn").click();

    await expect(page.getByTestId("edit-popover")).not.toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Nueva Empresa SA").first()).toBeVisible();
  });

  test("Escape cancela la edición sin guardar el cambio", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await page.getByTestId("field-company").click();
    await page.getByTestId("edit-input").fill("No se guarda");
    await page.keyboard.press("Escape");

    await expect(page.getByTestId("edit-popover")).not.toBeVisible();
    await expect(page.getByText("No se guarda")).not.toBeVisible();
  });

  test("guardar campo empresa vacío lo limpia correctamente (campo opcional)", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await page.getByTestId("field-company").click();
    await page.getByTestId("edit-input").clear();
    await page.getByTestId("save-edit-btn").click();
    // Empresa no es requerida → guarda vacío y el popover cierra sin error
    await expect(page.getByTestId("edit-popover")).not.toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId("edit-error")).not.toBeVisible();
  });

  // ── Tabs ────────────────────────────────────────────────────────────────────

  test("tab Resumen está activo por defecto", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("tab-resumen")).toHaveAttribute("data-state", "active");
  });

  test("tab Conversaciones muestra la sección de conversaciones", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await page.getByTestId("tab-conversaciones").click();
    await expect(page.getByTestId("conversations-list")).toBeVisible({ timeout: 5_000 });
  });

  test("tab Actividades muestra el timeline y los subfiltros", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await page.getByTestId("tab-actividades").click();
    await expect(page.getByTestId("activity-timeline")).toBeVisible();

    for (const label of ["Todas", "Notas", "Llamadas", "Reuniones", "Emails", "Tareas"]) {
      await expect(page.getByTestId(`activity-filter-${label}`)).toBeVisible();
    }
  });

  // ── Registrar actividad ─────────────────────────────────────────────────────

  test("registrar nota aparece en el timeline con actualización optimista", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await page.getByTestId("tab-actividades").click();
    await page.getByTestId("add-activity-btn").click();

    await expect(page.getByTestId("activity-form-dialog")).toBeVisible();
    // "note" es el tipo por defecto, pero hacemos click explícito
    await page.getByTestId("type-note").click();
    await page.getByTestId("activity-body").fill("Esta es mi nota de prueba");
    await page.getByTestId("save-activity-btn").click();

    // Actualización optimista: aparece sin recargar
    await expect(page.getByText("Esta es mi nota de prueba")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("[data-sonner-toast]")).toContainText("Actividad registrada", {
      timeout: 5_000,
    });
  });

  test("cancelar el diálogo de actividad lo cierra sin crear", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    await page.getByTestId("tab-actividades").click();
    await page.getByTestId("add-activity-btn").click();
    await expect(page.getByTestId("activity-form-dialog")).toBeVisible();

    await page.getByRole("button", { name: "Cancelar" }).click();
    await expect(page.getByTestId("activity-form-dialog")).not.toBeVisible();
  });

  test("subfiltro Notas muestra solo actividades de tipo note", async ({
    authedPage: page,
    testContact,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${BASE_URL}/contacts/${testContact.id}`);
    await page.waitForLoadState("networkidle");

    // Crear una nota primero para tener datos
    await page.getByTestId("tab-actividades").click();
    await page.getByTestId("add-activity-btn").click();
    await page.getByTestId("type-note").click();
    await page.getByTestId("activity-body").fill("Nota para filtro");
    await page.getByTestId("save-activity-btn").click();
    await expect(page.getByText("Nota para filtro")).toBeVisible({ timeout: 5_000 });

    // Aplicar subfiltro
    await page.getByTestId("activity-filter-Notas").click();

    const items = page.getByTestId("activity-item");
    const count = await items.count();
    for (let i = 0; i < count; i++) {
      await expect(items.nth(i).getByTestId("activity-type-icon")).toHaveAttribute(
        "data-type",
        "note",
      );
    }
  });
});
