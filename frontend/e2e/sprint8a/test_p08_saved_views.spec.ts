/**
 * P-08 — Playwright E2E: módulo de vistas guardadas (Sprint 8A)
 *
 * Cubre: sidebar de vistas, crear vista, aplicar filtros, eliminar vista,
 * estado deshabilitado del botón "Guardar vista" y comportamiento en mobile.
 *
 * Adaptaciones al spec original:
 *   - Import desde sprint8a/fixtures (no sprint7/fixtures directamente)
 *   - `page.getByLabel('Nombre')` en vez de getByPlaceholder (placeholder cambia)
 *   - `page.getByTestId('save-view-btn')` para el botón de guardar vista
 *   - `page.getByTestId('view-menu-btn')` para el menú de 3 puntos
 *   - La eliminación no muestra confirmación → test verifica desaparición de la vista
 *   - El sidebar en mobile está `hidden md:flex` → oculto sin toggle
 *
 * Prerrequisitos:
 *   - Frontend: npm run dev (puerto 5173)
 *   - Backend: uvicorn app.main:app (puerto 8000)
 *   - Credenciales en env: TEST_OWNER_EMAIL, TEST_OWNER_PASSWORD
 */

import { test, expect, createSavedView, deleteSavedView } from "./fixtures";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173";

// ── P-08-01 ───────────────────────────────────────────────────────────────────

test("sidebar de vistas es visible en /contacts (desktop)", async ({
  authedPage: page,
}) => {
  await page.goto(`${BASE_URL}/contacts`);
  await expect(page.getByTestId("contacts-header")).toBeVisible();

  // En desktop, el sidebar debe mostrar "Mis vistas"
  await expect(page.getByText("Mis vistas")).toBeVisible();
  await expect(page.getByTestId("saved-views-sidebar")).toBeVisible();
});

// ── P-08-02 ───────────────────────────────────────────────────────────────────

test("crear vista guardada con filtro de status", async ({
  authedPage: page,
  ownerToken,
}) => {
  await page.goto(`${BASE_URL}/contacts`);

  // Abrir panel de filtros y aplicar uno de status
  await page.getByTestId("filters-toggle-btn").click();
  await expect(page.getByTestId("filters-panel")).toBeVisible();
  await page.getByTestId("status-filter-calificado").click();

  // El badge de filtros activos debe aparecer
  await expect(page.getByTestId("filter-count-badge")).toBeVisible();

  // El botón "Guardar vista" debe estar habilitado
  const saveBtn = page.getByTestId("save-view-btn");
  await expect(saveBtn).toBeEnabled();
  await saveBtn.click();

  // Diálogo para nombrar la vista
  const nameInput = page.getByLabel("Nombre");
  await expect(nameInput).toBeVisible();
  await nameInput.fill("E2E Mis Calificados");

  // Enviar
  await page.getByRole("button", { name: /guardar vista/i, exact: false }).last().click();

  // La vista debe aparecer en el sidebar
  await expect(page.getByText("E2E Mis Calificados")).toBeVisible({ timeout: 5000 });

  // Cleanup: borrar la vista creada
  const views = await page.evaluate(async (token) => {
    const r = await fetch("http://localhost:8000/api/v1/contacts/views", {
      headers: { Authorization: `Bearer ${token}` },
    });
    return r.json() as Promise<Array<{ id: string; name: string }>>;
  }, ownerToken);
  const created = views.find((v) => v.name === "E2E Mis Calificados");
  if (created) await deleteSavedView(ownerToken, created.id);
});

// ── P-08-03 ───────────────────────────────────────────────────────────────────

test("aplicar vista guardada restaura filtros (badge visible)", async ({
  authedPage: page,
  ownerToken,
  savedView,
}) => {
  // savedView fixture crea {"status": ["nuevo"]} como filtro
  await page.goto(`${BASE_URL}/contacts`);

  // Hacer clic en la vista guardada en el sidebar
  const viewItem = page
    .getByTestId("view-item")
    .filter({ hasText: savedView.name });
  await expect(viewItem).toBeVisible({ timeout: 5000 });
  await viewItem.click();

  // El badge de filtros activos debe aparecer (la vista tenía filtros)
  if (Object.keys(savedView.filters).length > 0) {
    await expect(page.getByTestId("filter-count-badge")).toBeVisible({
      timeout: 3000,
    });
  }
});

// ── P-08-04 ───────────────────────────────────────────────────────────────────

test("eliminar vista la remueve del sidebar", async ({
  authedPage: page,
  ownerToken,
}) => {
  // Crear una vista temporal para este test
  const tmpView = await createSavedView(ownerToken, {
    name: "E2E Vista Temporal Para Borrar",
    filters: {},
    viewMode: "list",
  });

  await page.goto(`${BASE_URL}/contacts`);

  // La vista debe aparecer en el sidebar
  const viewItem = page
    .getByTestId("view-item")
    .filter({ hasText: tmpView.name });
  await expect(viewItem).toBeVisible({ timeout: 5000 });

  // Hover sobre el item para que aparezca el botón de menú
  await viewItem.hover();

  // Abrir el menú de 3 puntos (el botón puede estar invisible hasta hover)
  const menuBtn = viewItem.getByTestId("view-menu-btn");
  await menuBtn.click({ force: true });

  // Hacer clic en "Eliminar"
  await page.getByRole("menuitem", { name: /eliminar/i }).click();

  // La vista debe desaparecer del sidebar (eliminación directa, sin confirmación)
  await expect(viewItem).not.toBeVisible({ timeout: 5000 });
});

// ── P-08-05 ───────────────────────────────────────────────────────────────────

test("botón guardar vista deshabilitado sin filtros activos", async ({
  authedPage: page,
}) => {
  await page.goto(`${BASE_URL}/contacts`);

  // Sin filtros, el botón debe estar deshabilitado
  const saveBtn = page.getByTestId("save-view-btn");
  await expect(saveBtn).toBeVisible();
  await expect(saveBtn).toBeDisabled();
});

// ── P-08-06 ───────────────────────────────────────────────────────────────────

test("sidebar está oculto en mobile (< 768px)", async ({ authedPage: page }) => {
  // Simular viewport mobile
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`${BASE_URL}/contacts`);

  // En mobile el sidebar se oculta con `hidden md:flex`
  await expect(page.getByTestId("saved-views-sidebar")).not.toBeVisible();

  // El contenido principal sigue visible
  await expect(page.getByTestId("contacts-header")).toBeVisible();
});

// ── P-08-07 ───────────────────────────────────────────────────────────────────

test("sidebar colapsable — botón de colapsar funciona", async ({
  authedPage: page,
}) => {
  await page.goto(`${BASE_URL}/contacts`);

  // Desktop: sidebar visible con "Mis vistas"
  await expect(page.getByText("Mis vistas")).toBeVisible();

  // Hacer clic en el botón de colapsar
  await page.getByTestId("sidebar-collapse-btn").click();

  // "Mis vistas" ya no debe ser visible (sidebar colapsado)
  await expect(page.getByText("Mis vistas")).not.toBeVisible({ timeout: 2000 });

  // El botón de expandir debe aparecer
  await expect(page.getByTestId("sidebar-expand-btn")).toBeVisible();

  // Expandir nuevamente
  await page.getByTestId("sidebar-expand-btn").click();
  await expect(page.getByText("Mis vistas")).toBeVisible({ timeout: 2000 });
});

// ── P-08-08 ───────────────────────────────────────────────────────────────────

test("vista marcada como default aparece primera en el sidebar", async ({
  authedPage: page,
  ownerToken,
}) => {
  // Crear dos vistas: una normal y una default
  const normal = await createSavedView(ownerToken, {
    name: "E2E Vista Normal",
    filters: {},
    viewMode: "list",
    isDefault: false,
  });
  const defaultView = await createSavedView(ownerToken, {
    name: "E2E Vista Principal",
    filters: {},
    viewMode: "list",
    isDefault: true,
  });

  await page.goto(`${BASE_URL}/contacts`);

  // La vista default debe aparecer primera (is_default DESC en el orden)
  const items = page.getByTestId("view-item");
  await expect(items.first()).toContainText("E2E Vista Principal", {
    timeout: 5000,
  });

  // Cleanup
  await deleteSavedView(ownerToken, normal.id);
  await deleteSavedView(ownerToken, defaultView.id);
});

// ── P-08-09 ───────────────────────────────────────────────────────────────────

test("estado vacío del sidebar muestra mensaje de ayuda", async ({
  authedPage: page,
  ownerToken,
}) => {
  // Borrar todas las vistas del usuario
  const views = await page.evaluate(async (token) => {
    const r = await fetch("http://localhost:8000/api/v1/contacts/views", {
      headers: { Authorization: `Bearer ${token}` },
    });
    return r.json() as Promise<Array<{ id: string }>>;
  }, ownerToken);
  await Promise.all(views.map((v) => deleteSavedView(ownerToken, v.id)));

  await page.goto(`${BASE_URL}/contacts`);

  // El estado vacío debe mostrar el mensaje de ayuda
  await expect(
    page.getByText(/guarda combinaciones de filtros/i)
  ).toBeVisible({ timeout: 5000 });
});

// ── P-08-10 ───────────────────────────────────────────────────────────────────

test("renombrar vista via menú contextual", async ({
  authedPage: page,
  ownerToken,
}) => {
  const view = await createSavedView(ownerToken, {
    name: "E2E Vista Para Renombrar",
    filters: {},
    viewMode: "list",
  });

  await page.goto(`${BASE_URL}/contacts`);
  const viewItem = page
    .getByTestId("view-item")
    .filter({ hasText: view.name });
  await expect(viewItem).toBeVisible({ timeout: 5000 });
  await viewItem.hover();

  const menuBtn = viewItem.getByTestId("view-menu-btn");
  await menuBtn.click({ force: true });
  await page.getByRole("menuitem", { name: /renombrar/i }).click();

  // El diálogo de renombrar debe aparecer con el nombre actual
  const nameInput = page.getByLabel("Nombre");
  await expect(nameInput).toBeVisible();
  await nameInput.fill("E2E Vista Renombrada");
  await page.getByRole("button", { name: /guardar vista/i, exact: false }).last().click();

  // El nuevo nombre debe aparecer en el sidebar
  await expect(page.getByText("E2E Vista Renombrada")).toBeVisible({ timeout: 5000 });

  // Cleanup
  await deleteSavedView(ownerToken, view.id);
});
