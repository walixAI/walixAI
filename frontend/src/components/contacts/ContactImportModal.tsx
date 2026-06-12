import { useState, useRef, useEffect, useCallback } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  UploadCloud,
  X,
  CheckCircle2,
  AlertTriangle,
  Download,
  Loader2,
  FileText,
  ArrowLeft,
} from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { importContacts, getImportJob } from "@/lib/queries/contacts";

// ── Types ─────────────────────────────────────────────────────────────────────

type ImportStep = "upload" | "preview" | "progress" | "result";

interface ParsedCSV {
  headers: string[];
  previewRows: string[][];
  totalRows: number;
}

interface JobState {
  processed: number;
  total: number;
  errors: ImportError[];
  errorCsvBase64?: string;
  failed?: boolean;
}

interface ImportError {
  row?: number;
  reason?: string;
  message?: string;
  [key: string]: unknown;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const ACCEPTED_COLUMNS = new Set([
  "nombre", "apellido", "telefono", "empresa", "fuente", "status",
]);
const REQUIRED_COLUMN = "nombre";
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const POLL_INTERVAL_MS = 1500;

const TEMPLATE_CSV =
  "﻿" + // UTF-8 BOM for Excel compatibility
  "nombre,apellido,telefono,empresa,fuente\n" +
  "Juan,García,+521234567890,ACME S.A.,manual\n" +
  "María,López,+521098765432,Empresa XYZ,whatsapp_inbound\n";

// ── CSV helpers ───────────────────────────────────────────────────────────────

function parseCSVPreview(text: string): ParsedCSV {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  if (lines.length === 0) return { headers: [], previewRows: [], totalRows: 0 };

  const parseRow = (line: string): string[] => {
    const result: string[] = [];
    let cur = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') { inQuotes = !inQuotes; continue; }
      if (ch === "," && !inQuotes) { result.push(cur); cur = ""; continue; }
      cur += ch;
    }
    result.push(cur);
    return result.map((s) => s.trim());
  };

  const headers = parseRow(lines[0]).map((h) => h.toLowerCase());
  const dataLines = lines.slice(1);
  const previewRows = dataLines.slice(0, 5).map(parseRow);

  return { headers, previewRows, totalRows: dataLines.length };
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function downloadTemplate() {
  downloadBlob(
    new Blob([TEMPLATE_CSV], { type: "text/csv;charset=utf-8;" }),
    "plantilla-contactos-walix.csv",
  );
}

function downloadErrorCsv(base64: string) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  downloadBlob(
    new Blob([bytes], { type: "text/csv;charset=utf-8;" }),
    "errores-importacion-walix.csv",
  );
}

// ── Step components ───────────────────────────────────────────────────────────

interface UploadStepProps {
  onFile: (file: File, parsed: ParsedCSV) => void;
  fileError: string | null;
  setFileError: (e: string | null) => void;
}

function UploadStep({ onFile, fileError, setFileError }: UploadStepProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const processFile = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      setFileError(null);

      if (!file.name.toLowerCase().endsWith(".csv")) {
        setFileError("Solo se aceptan archivos CSV (.csv).");
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setFileError("El archivo supera el tamaño máximo de 10 MB.");
        return;
      }

      const reader = new FileReader();
      reader.onload = (e) => {
        const text = (e.target?.result as string) ?? "";
        const firstLines = text.split(/\r?\n/).slice(0, 6).join("\n");
        const parsed = parseCSVPreview(firstLines);

        if (!parsed.headers.includes(REQUIRED_COLUMN)) {
          setFileError(
            `El archivo debe tener una columna "${REQUIRED_COLUMN}". Columnas detectadas: ${parsed.headers.join(", ") || "(ninguna)"}.`,
          );
          return;
        }

        // Re-parse the full text to get actual total rows
        const fullParsed = parseCSVPreview(text);
        onFile(file, fullParsed);
      };
      reader.readAsText(file, "utf-8");
    },
    [onFile, setFileError],
  );

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    processFile(e.dataTransfer.files[0]);
  };

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        data-testid="csv-dropzone"
        onClick={() => inputRef.current?.click()}
        onDragEnter={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-10 cursor-pointer transition-colors",
          isDragging
            ? "border-primary bg-primary/5"
            : "border-border bg-muted/30 hover:bg-muted/50",
        )}
      >
        <UploadCloud
          className={cn(
            "h-10 w-10 transition-colors",
            isDragging ? "text-primary" : "text-muted-foreground",
          )}
        />
        <div className="text-center">
          <p className="text-sm font-medium">
            {isDragging ? "Suelta el archivo aquí" : "Arrastra tu CSV aquí"}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            o haz click para seleccionarlo · máx. 10 MB
          </p>
        </div>
      </div>

      <input
        data-testid="csv-file-input"
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => processFile(e.target.files?.[0])}
      />

      {/* Validation error */}
      {fileError && (
        <div data-testid="csv-error" className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-xs text-destructive">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>{fileError}</span>
        </div>
      )}

      {/* Template download */}
      <button
        data-testid="download-template-btn"
        type="button"
        onClick={downloadTemplate}
        className="flex items-center gap-1.5 text-xs text-primary hover:underline"
      >
        <Download className="h-3 w-3" />
        Descargar plantilla CSV
      </button>
    </div>
  );
}

// ── Preview step ──────────────────────────────────────────────────────────────

interface PreviewStepProps {
  file: File;
  parsed: ParsedCSV;
  onBack: () => void;
  onImport: () => Promise<void>;
  importing: boolean;
}

function PreviewStep({ file, parsed, onBack, onImport, importing }: PreviewStepProps) {
  const unknownCols = parsed.headers.filter((h) => !ACCEPTED_COLUMNS.has(h));

  return (
    <div className="space-y-4">
      {/* File info */}
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2">
        <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
        <span className="text-sm truncate flex-1">{file.name}</span>
        <span className="text-xs text-muted-foreground shrink-0">
          {parsed.totalRows} filas
        </span>
      </div>

      {/* Unknown columns warning */}
      {unknownCols.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700 px-3 py-2.5 text-xs text-amber-800 dark:text-amber-300">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>
            Las columnas <strong>{unknownCols.join(", ")}</strong> no son reconocidas y serán ignoradas.
          </span>
        </div>
      )}

      {/* Preview table */}
      <div>
        <p className="text-xs font-medium text-muted-foreground mb-1.5">
          Primeras {parsed.previewRows.length} de {parsed.totalRows} filas:
        </p>
        <div data-testid="preview-table" className="rounded-md border border-border overflow-hidden">
          <div className="overflow-x-auto max-h-48">
            <Table>
              <TableHeader>
                <TableRow>
                  {parsed.headers.map((h) => (
                    <TableHead key={h} className="text-[11px] h-8">
                      <span className={cn(!ACCEPTED_COLUMNS.has(h) && "text-muted-foreground line-through")}>
                        {h}
                      </span>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {parsed.previewRows.map((row, i) => (
                  <TableRow key={i}>
                    {row.map((cell, j) => (
                      <TableCell key={j} className="text-xs py-1.5 max-w-[120px] truncate">
                        {cell || <span className="text-muted-foreground italic">—</span>}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>

      {/* Total info */}
      <p data-testid="preview-count" className="text-sm text-center text-muted-foreground">
        Se importarán{" "}
        <span className="font-semibold text-foreground">{parsed.totalRows}</span>{" "}
        contactos
      </p>

      {/* Actions */}
      <div className="flex gap-2 justify-end">
        <Button data-testid="back-to-upload-btn" variant="outline" onClick={onBack} disabled={importing} className="gap-1.5">
          <ArrowLeft className="h-3.5 w-3.5" />
          Cambiar archivo
        </Button>
        <Button data-testid="confirm-import-btn" onClick={onImport} disabled={importing} className="gap-1.5">
          {importing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Importar {parsed.totalRows} contactos →
        </Button>
      </div>
    </div>
  );
}

// ── Progress step ─────────────────────────────────────────────────────────────

function ProgressStep({ job }: { job: JobState | null }) {
  const processed = job?.processed ?? 0;
  const total = job?.total ?? 0;
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;

  return (
    <div data-testid="import-progress" className="space-y-5 py-4">
      <div className="flex items-center justify-center gap-3">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
        <p className="text-sm font-medium">Importando contactos…</p>
      </div>
      <Progress value={pct} className="h-2" />
      <p className="text-center text-xs text-muted-foreground">
        {processed} de {total} contactos procesados ({pct}%)
      </p>
    </div>
  );
}

// ── Result step ───────────────────────────────────────────────────────────────

interface ResultStepProps {
  job: JobState;
  onDone: () => void;
}

function ResultStep({ job, onDone }: ResultStepProps) {
  const errorCount = job.errors.length;
  const success = errorCount === 0 && !job.failed;
  const visibleErrors = job.errors.slice(0, 5);

  return (
    <div data-testid="import-result" className="space-y-4">
      {/* Status icon + message */}
      <div className="flex flex-col items-center gap-2 py-3 text-center">
        {success ? (
          <CheckCircle2 className="h-10 w-10 text-green-500" />
        ) : (
          <AlertTriangle className="h-10 w-10 text-amber-500" />
        )}
        {success ? (
          <p className="text-sm font-medium">
            ¡Importación completada!{" "}
            <span className="text-green-600 dark:text-green-400">{job.processed} contactos</span>{" "}
            agregados correctamente.
          </p>
        ) : (
          <p className="text-sm font-medium">
            Se importaron{" "}
            <span className="font-semibold">{job.processed}</span> contactos con{" "}
            <span className="text-destructive font-semibold">{errorCount} error{errorCount !== 1 ? "es" : ""}</span>.
          </p>
        )}
      </div>

      {/* Error list */}
      {visibleErrors.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">
            Primeros {visibleErrors.length} errores:
          </p>
          <div className="rounded-md border border-destructive/20 bg-destructive/5 divide-y divide-destructive/10">
            {visibleErrors.map((err, i) => (
              <div key={i} className="px-3 py-1.5 text-xs">
                {err.row != null && (
                  <span className="font-mono text-muted-foreground mr-1.5">Fila {err.row}:</span>
                )}
                <span className="text-destructive">
                  {err.reason ?? err.message ?? JSON.stringify(err)}
                </span>
              </div>
            ))}
          </div>
          {job.errors.length > 5 && (
            <p className="text-xs text-muted-foreground">
              … y {job.errors.length - 5} error{job.errors.length - 5 !== 1 ? "es" : ""} más
            </p>
          )}
        </div>
      )}

      {/* Download error CSV */}
      {job.errorCsvBase64 && (
        <Button
          variant="outline"
          size="sm"
          className="w-full gap-1.5 text-xs"
          onClick={() => downloadErrorCsv(job.errorCsvBase64!)}
        >
          <Download className="h-3.5 w-3.5" />
          Descargar CSV de errores
        </Button>
      )}

      <Button data-testid="import-done-btn" className="w-full" onClick={onDone}>
        Listo
      </Button>
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────────

interface ContactImportModalProps {
  open: boolean;
  onClose: () => void;
  onImportComplete: (importedCount: number) => void;
}

export function ContactImportModal({
  open,
  onClose,
  onImportComplete,
}: ContactImportModalProps) {
  const qc = useQueryClient();
  const [step, setStep] = useState<ImportStep>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<ParsedCSV | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobState, setJobState] = useState<JobState | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Reset on open
  useEffect(() => {
    if (open) {
      setStep("upload");
      setFile(null);
      setParsed(null);
      setFileError(null);
      setImporting(false);
      setJobId(null);
      setJobState(null);
    } else {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
    }
  }, [open]);

  // Polling in progress step
  useEffect(() => {
    if (step !== "progress" || !jobId) return;

    const poll = async () => {
      try {
        const result = await getImportJob(jobId);
        const errors = (result.errors ?? []) as ImportError[];

        const next: JobState = {
          processed: result.processed,
          total: result.total,
          errors,
          errorCsvBase64: result.errorCsvBase64,
          failed: result.status === "failed",
        };
        setJobState(next);

        if (result.status === "completed" || result.status === "failed") {
          clearInterval(intervalRef.current!);
          intervalRef.current = null;
          setStep("result");
        }
      } catch {
        // transient error — keep polling
      }
    };

    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => { clearInterval(intervalRef.current!); intervalRef.current = null; };
  }, [step, jobId]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleFileSelected = useCallback((f: File, p: ParsedCSV) => {
    setFile(f);
    setParsed(p);
    setFileError(null);
    setStep("preview");
  }, []);

  const handleImport = useCallback(async () => {
    if (!file) return;
    setImporting(true);
    try {
      const { jobId: id, totalRows } = await importContacts(file);
      setJobId(id);
      setJobState({ processed: 0, total: totalRows, errors: [] });
      setStep("progress");
    } catch (e: unknown) {
      toast.error("Error al iniciar la importación", {
        description: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setImporting(false);
    }
  }, [file]);

  const handleDone = useCallback(() => {
    const count = jobState?.processed ?? 0;
    qc.invalidateQueries({ queryKey: ["contacts"] });
    toast.success(`Importación completada — ${count} contactos`);
    onImportComplete(count);
    onClose();
  }, [jobState, qc, onImportComplete, onClose]);

  // ── Lock close during steps 2 and 3 ─────────────────────────────────────────
  const locked = step === "preview" || step === "progress";
  const showClose = !locked;

  const TITLES: Record<ImportStep, string> = {
    upload:   "Importar contactos",
    preview:  "Vista previa del archivo",
    progress: "Importando…",
    result:   "Resultado de la importación",
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <DialogPrimitive.Root open={open} onOpenChange={(v) => { if (!v && !locked) onClose(); }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          data-testid="import-modal"
          onInteractOutside={(e) => { if (locked) e.preventDefault(); }}
          onEscapeKeyDown={(e) => { if (locked) e.preventDefault(); }}
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-background p-6 shadow-xl duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]"
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-semibold leading-none">{TITLES[step]}</h2>
              {step !== "progress" && (
                <p className="text-xs text-muted-foreground mt-1">
                  {step === "upload"   && "Sube un CSV con tus contactos"}
                  {step === "preview"  && "Revisa los datos antes de importar"}
                  {step === "result"   && "Importación finalizada"}
                </p>
              )}
            </div>
            {showClose && (
              <button
                type="button"
                onClick={onClose}
                className="rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                aria-label="Cerrar"
              >
                <X className="h-4 w-4" />
                <span className="sr-only">Cerrar</span>
              </button>
            )}
          </div>

          {/* Step indicator */}
          <div className="flex items-center gap-1.5 mb-5">
            {(["upload", "preview", "progress", "result"] as ImportStep[]).map((s, i) => (
              <div
                key={s}
                className={cn(
                  "h-1 flex-1 rounded-full transition-colors",
                  i === 0 && (step === "upload" ? "bg-primary" : "bg-primary"),
                  i === 1 && (["preview", "progress", "result"].includes(step) ? "bg-primary" : "bg-muted"),
                  i === 2 && (["progress", "result"].includes(step) ? "bg-primary" : "bg-muted"),
                  i === 3 && (step === "result" ? "bg-primary" : "bg-muted"),
                )}
              />
            ))}
          </div>

          {/* Step content */}
          {step === "upload" && (
            <UploadStep
              onFile={handleFileSelected}
              fileError={fileError}
              setFileError={setFileError}
            />
          )}

          {step === "preview" && file && parsed && (
            <PreviewStep
              file={file}
              parsed={parsed}
              onBack={() => { setFile(null); setParsed(null); setStep("upload"); }}
              onImport={handleImport}
              importing={importing}
            />
          )}

          {step === "progress" && <ProgressStep job={jobState} />}

          {step === "result" && jobState && (
            <ResultStep job={jobState} onDone={handleDone} />
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
