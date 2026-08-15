/**
 * E2E — Redirect de la ruta legacy /reports.
 *
 * Código auditado: frontend/src/App.tsx línea 100:
 *   <Route path="/reports" element={<Navigate to="/dashboard?panel=desempeno" replace />} />
 * dentro del grupo de rutas protegidas (ProtectedRoute + AppLayout), ANTES
 * de la ruta catch-all `<Route path="*" element={<NotFound />} />`.
 *
 * Por cómo matchea react-router-dom v6 (<Routes>), "/reports" resuelve
 * directo a este elemento Navigate — la ruta "*" (NotFound) nunca entra en
 * consideración para esta URL. No es una condición de carrera ni depende de
 * timing: es una garantía estructural del árbol de rutas. El test igual lo
 * verifica en runtime por si esa garantía se rompe en un refactor futuro
 * (p. ej. si alguien reordena las rutas o mueve "/reports" fuera del grupo).
 *
 * Requiere: backend en :8000, frontend en :3000, seed.py ya corrido.
 * Ejecución: npx playwright test e2e/regression/redirect_legacy.spec.ts
 */

import { test, expect, type Page } from "@playwright/test";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

const OWNER = {
  email: process.env.TEST_REDIRECT_EMAIL ?? "owner@clinica.com",
  password: process.env.TEST_REDIRECT_PASSWORD ?? "walix2026",
};

async function dismissWelcomeTourIfPresent(page: Page): Promise<void> {
  // OnboardingTour.tsx guarda "visto" en localStorage por user id — cada
  // browser context nuevo de Playwright dispara el modal "Tour de
  // bienvenida" en la primera visita, tapando toda la pantalla.
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
  await page.getByLabel(/correo|email/i).fill(OWNER.email);
  await page.getByLabel(/contraseña|password/i).fill(OWNER.password);
  await page.getByRole("button", { name: /iniciar sesión|entrar|login/i }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
  await dismissWelcomeTourIfPresent(page);
}

test.describe("Redirect legacy — /reports", () => {
  test("navegar a /reports redirige a /dashboard?panel=desempeno sin pasar por 404", async ({
    page,
  }) => {
    // Se captura CADA respuesta de documento/navegación para probar que en
    // ningún momento del ciclo de vida se sirvió la página de NotFound.
    const notFoundSeen: string[] = [];
    page.on("console", (msg) => {
      if (msg.text().includes("404 Error: User attempted to access non-existent route")) {
        notFoundSeen.push(msg.text());
      }
    });

    await login(page);
    await page.goto(`${BASE_URL}/reports`);

    await page.waitForURL(`${BASE_URL}/dashboard?panel=desempeno`, { timeout: 10_000 });
    await expect(page).toHaveURL(`${BASE_URL}/dashboard?panel=desempeno`);

    // El tab "Desempeño" del PanelSwitcher queda activo — confirma que no
    // solo cambió la URL, sino que el Dashboard resolvió el panel correcto.
    await expect(page.getByRole("button", { name: "Desempeño", exact: true })).toHaveClass(
      /border-primary/,
      { timeout: 10_000 },
    );

    // El heading "404" / "Pagina no encontrada" de NotFound.tsx nunca debe
    // haber aparecido en el DOM, y su console.error tampoco debe haberse
    // disparado (ver NotFound.tsx: se loguea en un useEffect al montar).
    await expect(page.getByText("404", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/pagina no encontrada/i)).toHaveCount(0);
    expect(notFoundSeen).toHaveLength(0);
  });
});
