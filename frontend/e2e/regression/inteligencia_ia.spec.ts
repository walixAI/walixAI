/**
 * E2E — Widget "Inteligencia IA" ante error de red.
 *
 * Código auditado antes de escribir este test:
 *   - frontend/src/components/dashboard/AiIntelligenceSection.tsx — usa
 *     usePipelineIntelligence() (react-query). El único branch de error
 *     visible en el JSX es `if (isLoading || !data) return <skeleton>`; ese
 *     skeleton NO incluye el texto "Inteligencia IA" (ese <h3> solo existe
 *     DESPUÉS del early-return, en la rama de datos cargados) — así que
 *     esperar ese texto durante un error de red nunca resolvería.
 *   - frontend/src/lib/queries/pipelineIntelligence.ts — GET
 *     /api/metrics/pipeline-intelligence vía apiRequest.
 *   - frontend/src/lib/queries/_client.ts — apiRequest hace `throw new
 *     Error(...)` en cualquier !res.ok; App.tsx configura el QueryClient
 *     global con `retry: 0`.
 *
 * HALLAZGO no relacionado al fallback de red, encontrado al verificar en qué
 * panel vive este widget antes de escribir el test (no asumido desde el
 * comentario del código):
 *   - backend/alembic/versions/i4j5k6l7m8n9_dashboard_widget_ai_intelligence.py
 *     inserta la fila del catálogo con surface="principal".
 *   - frontend/src/components/dashboard/widgetRegistry.ts agrupa
 *     `ai_intelligence_section` bajo el comentario "// Panel: desempeno",
 *     junto a los demás widgets de ese panel.
 *   Verificado en runtime contra la DB real (GET /api/dashboard/layout):
 *   panel=desempeno NUNCA incluye "ai_intelligence_section" (ni para owner
 *   ni para ningún rol — DashboardWidget es un catálogo global, no
 *   por-tenant); panel=principal SÍ lo incluye, para cualquier rol (sin
 *   min_role). O sea: el widget "Inteligencia IA" es real y se puede probar,
 *   pero vive en Principal, no en Desempeño como sugiere el comentario del
 *   registry — posible desalineación entre la migración y el frontend, fuera
 *   de alcance arreglar acá. Este test navega a Principal porque es donde el
 *   widget REALMENTE se resuelve, no donde el comentario dice que debería
 *   estar.
 *
 * CONCLUSIÓN sobre el fallback en sí (comportamiento real, no el que
 * "debería" tener): ante un error de red/servidor en este endpoint, el
 * widget NO muestra un mensaje de error ni un banner de fallback — se queda
 * con el skeleton pulsante indefinidamente. El aviso "Mostrando datos de
 * demostración..." que sí existe en el componente (source === "fallback") es
 * para un caso DISTINTO: una respuesta 200 del backend cuyo JSON indica que
 * el propio servicio de IA no respondió — no un fallo de red del cliente.
 *
 * Requiere: backend en :8000, frontend en :3000, seed.py ya corrido.
 * Ejecución: npx playwright test e2e/regression/inteligencia_ia.spec.ts
 */

import { test, expect, type Page } from "@playwright/test";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

// El widget no tiene min_role — cualquier usuario autenticado lo ve en Principal.
const USER = {
  email: process.env.TEST_AI_WIDGET_EMAIL ?? "asesor.con@clinica.com",
  password: process.env.TEST_AI_WIDGET_PASSWORD ?? "walix2026",
};

async function dismissWelcomeTourIfPresent(page: Page): Promise<void> {
  // locator.isVisible({timeout}) NO hace polling (chequeo instantáneo pese a
  // aceptar `timeout`) — el modal abre 600ms después del mount, así que hay
  // que esperar activamente con waitFor, no con isVisible.
  const skipTour = page.getByRole("button", { name: /saltar tour/i });
  try {
    await skipTour.waitFor({ state: "visible", timeout: 8_000 });
    await skipTour.click();
  } catch {
    // El tour no apareció en la ventana de espera — nada que descartar.
  }
}

async function login(page: Page): Promise<void> {
  await page.goto(`${BASE_URL}/login`);
  await page.getByLabel(/correo|email/i).fill(USER.email);
  await page.getByLabel(/contraseña|password/i).fill(USER.password);
  await page.getByRole("button", { name: /iniciar sesión|entrar|login/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
  await dismissWelcomeTourIfPresent(page);
}

test.describe("Inteligencia IA — fallback ante error de red", () => {
  test("error 500 en /api/metrics/pipeline-intelligence no rompe la pantalla ni deja errores sin manejar", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => pageErrors.push(err.message));

    // Interceptar ANTES de navegar para no perder la primera carga del widget.
    await page.route("**/api/metrics/pipeline-intelligence**", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Simulated failure — Playwright regression test" }),
      }),
    );

    // login() ya termina en /dashboard (redirect post-login de la propia
    // app) — esa primera carga es la que dispara el fetch del widget, así
    // que la espera se arma ANTES de loguear, no con un goto adicional.
    const responsePromise = page.waitForResponse(
      (res) => res.url().includes("/api/metrics/pipeline-intelligence") && res.status() === 500,
      { timeout: 15_000 },
    );
    await login(page);
    const interceptedResponse = await responsePromise;
    expect(interceptedResponse.status()).toBe(500);

    // Comportamiento real: se queda en skeleton (placeholders pulsantes) — el
    // <h3>Inteligencia IA</h3> y el contenido real NUNCA se renderizan
    // durante un error, así que no hay nada de eso que buscar.
    await expect(page.getByText("Salud del Pipeline")).toHaveCount(0);
    await expect(page.getByText(/mostrando datos de demostración/i)).toHaveCount(0);

    // No pantalla rota: el ErrorBoundary global NO se disparó.
    await expect(page.getByText("Ups! Algo salio mal")).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);

    // El resto del panel Principal sigue funcionando con normalidad — otro
    // widget mandatorio del mismo panel (KpiCardsRow) debe renderizar.
    await expect(page.getByText("Valor del Pipeline")).toBeVisible({ timeout: 10_000 });

    // Sin errores de React/JS no manejados en consola ni excepciones de página.
    // (El 500 en sí genera actividad de red, pero no debe convertirse en una
    // excepción no capturada: react-query atrapa el throw de apiRequest.)
    expect(pageErrors, `pageerror inesperado: ${pageErrors.join(" | ")}`).toHaveLength(0);
    // Chromium loguea "Failed to load resource: ... 500" a console.error por
    // CUALQUIER respuesta HTTP no-2xx, automáticamente — es ruido esperado
    // del propio devtools ante el 500 que forzamos, no una excepción de JS
    // sin manejar. Lo que sí importaría detectar es un error real de React
    // (stack trace, "Uncaught", etc.), que esto no filtra.
    const unhandled = consoleErrors.filter(
      (e) =>
        !e.includes("Simulated failure") &&
        !/favicon/i.test(e) &&
        !/failed to load resource/i.test(e),
    );
    expect(unhandled, `console.error inesperado: ${unhandled.join(" | ")}`).toHaveLength(0);
  });
});
