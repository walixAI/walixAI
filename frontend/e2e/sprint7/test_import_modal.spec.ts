/**
 * P-11 — Playwright E2E: ContactImportModal — upload → preview → progreso → resultado
 *
 * Cubre: apertura del modal, descarga de plantilla, validaciones de archivo,
 * flujo completo de importación CSV y bloqueo del modal durante el procesamiento.
 *
 * Requiere servidor frontend + backend corriendo (ver fixtures.ts).
 */

import * as fs from "fs";
import * as path from "path";
import { test, expect, loginAs } from "./fixtures";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173";

// ── CSV helpers ───────────────────────────────────────────────────────────────

function createCsvFile(content: string, filename = "test.csv"): string {
  const filePath = path.join("/tmp", filename);
  fs.writeFileSync(filePath, content, "utf-8");
  return filePath;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe("Modal de importación CSV", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, "owner");
    await page.goto(`${BASE_URL}/contacts`);
    await page.waitForLoadState("networkidle");
  });

  // ── Paso 1: apertura y UI inicial ─────────────────────────────────────────

  test("botón Importar CSV abre el modal con el dropzone", async ({ page }) => {
    await page.getByTestId("import-csv-btn").click();
    await expect(page.getByTestId("import-modal")).toBeVisible();
    await expect(page.getByTestId("csv-dropzone")).toBeVisible();
  });

  test("modal en paso upload se cierra con Escape", async ({ page }) => {
    await page.getByTestId("import-csv-btn").click();
    await expect(page.getByTestId("import-modal")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("import-modal")).not.toBeVisible();
  });

  test("modal en paso preview está bloqueado — Escape no lo cierra", async ({ page }) => {
    const filePath = createCsvFile("nombre\nTest Bloqueo");
    await page.getByTestId("import-csv-btn").click();
    await page.getByTestId("csv-file-input").setInputFiles(filePath);
    await expect(page.getByTestId("preview-table")).toBeVisible();
    // En preview el modal está bloqueado
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("import-modal")).toBeVisible();
  });

  test("modal en paso preview está bloqueado — click fuera no lo cierra", async ({ page }) => {
    const filePath = createCsvFile("nombre\nTest Bloqueo");
    await page.getByTestId("import-csv-btn").click();
    await page.getByTestId("csv-file-input").setInputFiles(filePath);
    await expect(page.getByTestId("preview-table")).toBeVisible();
    // Click en el overlay (fuera del modal)
    await page.mouse.click(10, 10);
    await expect(page.getByTestId("import-modal")).toBeVisible();
  });

  // ── Descarga de plantilla ─────────────────────────────────────────────────

  test("descargar plantilla CSV genera un archivo .csv", async ({ page }) => {
    await page.getByTestId("import-csv-btn").click();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByTestId("download-template-btn").click(),
    ]);
    expect(download.suggestedFilename()).toContain(".csv");
  });

  // ── Validaciones de archivo ───────────────────────────────────────────────

  test("subir CSV sin columna nombre muestra error de validación", async ({ page }) => {
    const filePath = createCsvFile(
      "email,telefono\ntest@test.com,+521234567890",
      "bad.csv",
    );
    await page.getByTestId("import-csv-btn").click();
    await page.getByTestId("csv-file-input").setInputFiles(filePath);
    await expect(page.getByTestId("csv-error")).toContainText("nombre");
  });

  test("subir archivo que no es CSV muestra error de formato", async ({ page }) => {
    const filePath = path.join("/tmp", "test.txt");
    fs.writeFileSync(filePath, "esto no es csv");
    await page.getByTestId("import-csv-btn").click();
    await page.getByTestId("csv-file-input").setInputFiles(filePath);
    await expect(page.getByTestId("csv-error")).toContainText("CSV");
  });

  // ── Paso 2: preview ───────────────────────────────────────────────────────

  test("CSV válido avanza al paso preview con tabla y conteo de filas", async ({ page }) => {
    const csv = [
      "nombre,empresa,telefono",
      "Ana García,ACME,+5215512345678",
      "Carlos López,XYZ,+5215598765432",
      "Maria Pérez,,",
    ].join("\n");
    const filePath = createCsvFile(csv, "valid_preview.csv");

    await page.getByTestId("import-csv-btn").click();
    await page.getByTestId("csv-file-input").setInputFiles(filePath);

    await expect(page.getByTestId("preview-table")).toBeVisible();
    await expect(page.getByTestId("preview-count")).toContainText("3");
  });

  test("columnas desconocidas muestran advertencia en preview", async ({ page }) => {
    const csv = "nombre,columna_rara\nTest,valor\n";
    const filePath = createCsvFile(csv, "unknown_cols.csv");

    await page.getByTestId("import-csv-btn").click();
    await page.getByTestId("csv-file-input").setInputFiles(filePath);

    await expect(page.getByTestId("preview-table")).toBeVisible();
    await expect(page.getByText("columna_rara")).toBeVisible();
  });

  test("botón Cambiar archivo en preview vuelve al dropzone", async ({ page }) => {
    const filePath = createCsvFile("nombre\nTest Volver");
    await page.getByTestId("import-csv-btn").click();
    await page.getByTestId("csv-file-input").setInputFiles(filePath);
    await expect(page.getByTestId("preview-table")).toBeVisible();

    await page.getByTestId("back-to-upload-btn").click();
    await expect(page.getByTestId("csv-dropzone")).toBeVisible();
    await expect(page.getByTestId("preview-table")).not.toBeVisible();
  });

  // ── Flujo completo ────────────────────────────────────────────────────────

  test("flujo completo: upload → preview → progreso → resultado exitoso", async ({ page }) => {
    // Phones y nombres únicos por ejecución para evitar conflicto de clave única
    const ts = String(Date.now()).slice(-6); // 6 dígitos, cambia cada milisegundo
    const rows = Array.from(
      { length: 5 },
      (_, i) =>
        `Contacto PW${ts} ${i + 1},Empresa${i},+5215${ts}${String(i).padStart(2, "0")}`,
    );
    const csv = ["nombre,empresa,telefono", ...rows].join("\n");
    const filePath = createCsvFile(csv, "valid_import.csv");

    await page.getByTestId("import-csv-btn").click();

    // Paso 1 → sube archivo
    await page.getByTestId("csv-file-input").setInputFiles(filePath);

    // Paso 2 → preview
    await expect(page.getByTestId("preview-count")).toContainText("5");
    await page.getByTestId("confirm-import-btn").click();

    // Paso 3 → progreso
    await expect(page.getByTestId("import-progress")).toBeVisible();

    // Paso 4 → resultado (espera hasta 20 s para el procesamiento en CI)
    await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("import-result")).toContainText("5");

    // Cerrar y verificar que al menos uno aparece en la lista
    await page.getByTestId("import-done-btn").click();
    await expect(page.getByTestId("import-modal")).not.toBeVisible();
    await expect(page.getByText(`Contacto PW${ts} 1`).first()).toBeVisible({ timeout: 8_000 });
  });

  test("botón Listo en resultado cierra el modal", async ({ page }) => {
    // Importar un CSV mínimo para llegar al paso resultado
    const ts = String(Date.now()).slice(-8);
    const csv = `nombre\nContacto Cierre ${ts}`;
    const filePath = createCsvFile(csv, "close_test.csv");

    await page.getByTestId("import-csv-btn").click();
    await page.getByTestId("csv-file-input").setInputFiles(filePath);
    await page.getByTestId("confirm-import-btn").click();
    await expect(page.getByTestId("import-result")).toBeVisible({ timeout: 20_000 });

    await page.getByTestId("import-done-btn").click();
    await expect(page.getByTestId("import-modal")).not.toBeVisible();
  });
});
