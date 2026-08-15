/**
 * E2E — Navegación de paneles del Dashboard (consolidación Sprint 13/14).
 *
 * Código auditado antes de escribir estos tests:
 *   - frontend/src/pages/app/Dashboard.tsx — selectedPanel viene de
 *     useSearchParams("panel") (default "principal"); handlePanelChange hace
 *     setSearchParams(key === "principal" ? {} : { panel: key }).
 *   - frontend/src/components/dashboard/PanelSwitcher.tsx — renderiza los
 *     paneles que devuelve usePanels() (GET /api/dashboard/panels), que YA
 *     viene filtrado por rol desde el backend (_user_can_see_panel). Si el
 *     activePanel de la URL no está en esa lista, un useEffect hace
 *     onPanelChange("principal") — auto-corrección silenciosa, no error.
 *   - frontend/src/components/dashboard/LayoutRenderer.tsx — useQuery con
 *     queryKey ["dashboard-layout", panelKey]; al ser panelKey parte de la
 *     key, cambiar de panel SIEMPRE dispara un fetch nuevo a
 *     /api/dashboard/layout?panel=<key> (el bug de caché cruzada del Prompt 3
 *     ya no puede reproducirse: son entradas de caché distintas).
 *   - backend/app/api/dashboard_widgets.py — list_panels() filtra con
 *     _user_can_see_panel: excluye paneles con min_role > rol del usuario, y
 *     paneles custom (is_system=False) cuyo created_by no sea el usuario
 *     actual. El panel del sistema "desempeno" tiene min_role="owner" (ver
 *     backend/tests/regression/test_dashboard_panels.py, ya verificado ahí).
 *
 * Credenciales: seed real de scripts/seed.py (tenant admin@clinica.com,
 * password walix2026) — mismas que ya usa e2e/pipeline/pipeline.spec.ts.
 * asesor.con y asesor.sf son dos usuarios *distintos* del mismo tenant, útil
 * para probar el caso de panel ajeno sin necesitar un segundo tenant.
 *
 * Requiere: backend en :8000, frontend en :3000, seed.py ya corrido.
 * Ejecución: npx playwright test e2e/regression/navegacion_paneles.spec.ts
 */

import { test, expect, type Page } from "@playwright/test";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const API_URL = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000";

const OWNER = {
  email: process.env.TEST_PANELS_OWNER_EMAIL ?? "owner@clinica.com",
  password: process.env.TEST_PANELS_OWNER_PASSWORD ?? "walix2026",
};
// asesor.con: rol "asesor" (rank 40) — por debajo del min_role="owner" (rank 90) del panel Desempeño.
const ASESOR_A = {
  email: process.env.TEST_PANELS_ASESOR_A_EMAIL ?? "asesor.con@clinica.com",
  password: process.env.TEST_PANELS_ASESOR_A_PASSWORD ?? "walix2026",
};
// Segundo usuario del MISMO tenant, para el caso de panel custom ajeno.
const ASESOR_B = {
  email: process.env.TEST_PANELS_ASESOR_B_EMAIL ?? "asesor.sf@clinica.com",
  password: process.env.TEST_PANELS_ASESOR_B_PASSWORD ?? "walix2026",
};

// ── Auth helpers ──────────────────────────────────────────────────────────────

async function dismissWelcomeTourIfPresent(page: Page): Promise<void> {
  // OnboardingTour.tsx guarda "visto" en localStorage por user id, así que
  // CADA browser context nuevo de Playwright (sin ese localStorage) dispara
  // el modal "Tour de bienvenida" en la primera visita al dashboard, tapando
  // toda la pantalla. Sin este dismiss, cualquier click posterior se cuelga.
  //
  // OJO: useAutoOnboardingTour abre el modal recién 600ms después del mount
  // (setTimeout interno) — locator.isVisible({timeout}) NO hace polling (es
  // un chequeo instantáneo pese a aceptar `timeout`; ver docs de Playwright),
  // así que casi siempre lo encontraba "no visible todavía" y nunca lo
  // cerraba. waitFor({state:"visible"}) sí espera activamente.
  const skipTour = page.getByRole("button", { name: /saltar tour/i });
  try {
    await skipTour.waitFor({ state: "visible", timeout: 8_000 });
    await skipTour.click();
  } catch {
    // El tour no apareció en la ventana de espera — nada que descartar.
  }
}

async function login(page: Page, creds: { email: string; password: string }): Promise<string> {
  await page.goto(`${BASE_URL}/login`);
  await page.getByLabel(/correo|email/i).fill(creds.email);
  await page.getByLabel(/contraseña|password/i).fill(creds.password);
  await page.getByRole("button", { name: /iniciar sesión|entrar|login/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
  await dismissWelcomeTourIfPresent(page);
  return page.evaluate(
    () => localStorage.getItem("walix_token") ?? sessionStorage.getItem("walix_token") ?? "",
  );
}

async function getAuthToken(creds: { email: string; password: string }): Promise<string> {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(creds),
  });
  if (!res.ok) throw new Error(`login failed ${res.status}: ${await res.text()}`);
  const data = await res.json();
  return data.access_token as string;
}

// ── Panel API helpers ─────────────────────────────────────────────────────────

interface ApiPanel {
  id: string;
  key: string;
  name: string;
}

async function createPanelViaApi(token: string, name: string): Promise<ApiPanel> {
  const res = await fetch(`${API_URL}/api/dashboard/panels`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(`createPanel failed ${res.status}: ${await res.text()}`);
  return res.json();
}

async function deletePanelViaApi(token: string, id: string): Promise<void> {
  await fetch(`${API_URL}/api/dashboard/panels/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => undefined);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe("Navegación de paneles — Dashboard", () => {
  test("T1 — GET /dashboard carga el panel Principal por default", async ({ page }) => {
    // login() ya termina en /dashboard vía navigate() de React Router (SPA,
    // ver Login.tsx) — un page.goto() extra acá sería un hard reload
    // redundante que remonta la app entera y puede reabrir el tour.
    await login(page, OWNER);

    // Sin ?panel= en la URL — Dashboard.tsx usa "principal" como default.
    await expect(page).toHaveURL(/\/dashboard$/);

    const principalTab = page.getByRole("button", { name: "Principal", exact: true });
    await expect(principalTab).toBeVisible({ timeout: 10_000 });
    // Tab activo: border-primary text-foreground (ver PanelSwitcher.tsx).
    await expect(principalTab).toHaveClass(/border-primary/);
  });

  test("T2 — click en tab Desempeño actualiza la URL y dispara una carga de datos nueva", async ({
    page,
  }) => {
    await login(page, OWNER); // owner sí ve el panel Desempeño (min_role="owner")

    const desempenoTab = page.getByRole("button", { name: "Desempeño", exact: true });
    await expect(desempenoTab).toBeVisible({ timeout: 10_000 });

    // La prueba real del fix del Prompt 3: el click debe disparar un GET a
    // /api/dashboard/layout con panel=desempeno en la query — no basta con
    // que la UI cambie visualmente, tiene que haber tráfico de red nuevo.
    const [layoutRequest] = await Promise.all([
      page.waitForRequest(
        (req) => req.url().includes("/api/dashboard/layout") && req.url().includes("panel=desempeno"),
        { timeout: 20_000 },
      ),
      desempenoTab.click(),
    ]);
    expect(layoutRequest.url()).toContain("panel=desempeno");

    await expect(page).toHaveURL(/[?&]panel=desempeno/);
    await expect(desempenoTab).toHaveClass(/border-primary/);
  });

  test("T3 — usuario no-owner no ve el tab Desempeño (oculto, no deshabilitado)", async ({ page }) => {
    await login(page, ASESOR_A);

    await expect(page.getByRole("button", { name: "Principal", exact: true })).toBeVisible({
      timeout: 10_000,
    });
    // Confirmado en backend/app/api/dashboard_widgets.py: list_panels() filtra
    // el panel antes de devolverlo — el frontend nunca sabe que existe, así
    // que no hay botón deshabilitado, simplemente no está en el DOM.
    await expect(page.getByRole("button", { name: "Desempeño", exact: true })).toHaveCount(0);
  });

  test("T4 — crear panel custom vía CreatePanelDialog aparece en el switcher sin reload", async ({
    page,
  }) => {
    await login(page, OWNER);

    const panelName = `Panel E2E ${Date.now()}`;
    await page.getByRole("button", { name: "Crear panel" }).click();
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 5_000 });
    await page.locator("#panel-name").fill(panelName);
    await page.getByRole("button", { name: "Crear", exact: true }).click();

    // Timeouts generosos: el POST en sí es rápido (~1.5s medido en aislado),
    // pero T4 y T5 corren concurrentemente como el MISMO usuario owner contra
    // el Postgres real de Railway (no localhost) — bajo esa carga el
    // invalidateQueries + refetch que dispara el toast puede tardar más que
    // el 5s que se le daba antes.
    await expect(page.getByText(`Panel "${panelName}" creado`)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 3_000 });

    // Aparece en el switcher — sin haber navegado ni recargado la página.
    const newTab = page.getByRole("button", { name: panelName, exact: true });
    await expect(newTab).toBeVisible({ timeout: 10_000 });
    await expect(newTab).toHaveClass(/border-primary/); // onCreated activa el panel nuevo

    // Cleanup vía UI: borrar el panel recién creado para no ensuciar el tenant seed.
    await page.getByRole("button", { name: `Eliminar panel ${panelName}` }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Eliminar", exact: true }).click();
    await expect(page.getByText(`Panel "${panelName}" eliminado`)).toBeVisible({ timeout: 15_000 });
  });

  test("T5 — borrar panel custom propio lo hace desaparecer del switcher", async ({ page }) => {
    await login(page, OWNER);

    const panelName = `Panel Borrar E2E ${Date.now()}`;
    await page.getByRole("button", { name: "Crear panel" }).click();
    await page.locator("#panel-name").fill(panelName);
    await page.getByRole("button", { name: "Crear", exact: true }).click();
    const newTab = page.getByRole("button", { name: panelName, exact: true });
    // Mismo motivo que T4: bajo carga concurrente real, el refetch tras crear
    // puede tardar más que un timeout corto.
    await expect(newTab).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: `Eliminar panel ${panelName}` }).click();
    const confirmDialog = page.getByRole("alertdialog");
    await expect(confirmDialog).toBeVisible({ timeout: 3_000 });
    await confirmDialog.getByRole("button", { name: "Eliminar", exact: true }).click();

    await expect(page.getByRole("button", { name: panelName, exact: true })).toHaveCount(0);
    // Al borrar el panel activo, PanelSwitcher vuelve a "principal" (ver handleDelete).
    await expect(page.getByRole("button", { name: "Principal", exact: true })).toHaveClass(
      /border-primary/,
    );
  });

  test("T6 — ?panel=<key de otro usuario> no filtra datos ajenos", async ({ page }) => {
    const tokenA = await getAuthToken(ASESOR_A);
    const foreignPanel = await createPanelViaApi(tokenA, `Panel Privado ${Date.now()}`);

    try {
      // asesor.sf es OTRO usuario del MISMO tenant — no debería poder ver un
      // panel custom creado por asesor.con (created_by != user.id).
      await login(page, ASESOR_B);
      // A diferencia de T1-T5, este goto SÍ es necesario: es la única forma
      // de simular la manipulación manual de la URL con un panel ajeno.
      await page.goto(`${BASE_URL}/dashboard?panel=${encodeURIComponent(foreignPanel.key)}`);
      await dismissWelcomeTourIfPresent(page);

      // Comportamiento real documentado: usePanels() (filtrado por backend)
      // no incluye el panel ajeno → el useEffect de PanelSwitcher detecta que
      // activePanel no está en la lista y hace onPanelChange("principal"),
      // lo que limpia el query param. No es un 403 visible ni una página
      // rota — es una auto-corrección silenciosa a la URL sin el panel.
      await expect(page).toHaveURL(`${BASE_URL}/dashboard`, { timeout: 10_000 });
      await expect(page.getByRole("button", { name: "Principal", exact: true })).toHaveClass(
        /border-primary/,
      );
      // El nombre del panel ajeno no debe aparecer en ningún lado de la página.
      await expect(page.getByText(foreignPanel.name)).toHaveCount(0);
    } finally {
      await deletePanelViaApi(tokenA, foreignPanel.id);
    }
  });
});
