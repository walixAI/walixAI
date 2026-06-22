import { AlertTriangle } from "lucide-react";
import type { OppStaleRead } from "@/lib/api";

function formatMXN(n: string | number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const val = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(val)) return "—";
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

export function StaleBanner({ stale }: { stale: OppStaleRead }) {
  if (!stale || stale.count === 0) return null;

  return (
    <div
      role="status"
      className="flex items-center gap-3 px-4 py-3 rounded-xl border border-warning/30 bg-warning/5"
    >
      <AlertTriangle
        className="h-4 w-4 text-warning shrink-0"
        aria-hidden="true"
      />
      <p className="text-sm text-warning flex-1">
        <strong>{stale.count} oportunidad{stale.count !== 1 ? "es" : ""}</strong>{" "}
        sin actividad hace más de 10 días ({formatMXN(stale.total_amount)} en riesgo). Revísalas
        antes de que se enfríen.
      </p>
      <button
        type="button"
        className="shrink-0 text-xs font-medium text-warning underline underline-offset-2 hover:text-warning/80 focus-visible:ring-2 focus-visible:ring-warning rounded"
      >
        Ver insights IA
      </button>
    </div>
  );
}
