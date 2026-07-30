import { useQuery } from "@tanstack/react-query";
import { TrendingUp } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Pattern = {
  pattern_type: string;
  pattern_data: Record<string, unknown>;
  confidence_score: number;
  sample_size: number;
  updated_at: string;
};

function PatternContent({ pattern }: { pattern: Pattern }) {
  const { pattern_type, pattern_data } = pattern;

  if (pattern_type === "best_followup_day") {
    return (
      <p className="text-sm text-foreground">
        Mejor día de seguimiento:{" "}
        <span className="font-semibold capitalize">{String(pattern_data.day ?? "—")}</span>
      </p>
    );
  }

  if (pattern_type === "peak_response_hours") {
    const hours = Array.isArray(pattern_data.hours)
      ? (pattern_data.hours as number[]).map((h) => `${h}:00`).join(", ")
      : "—";
    return (
      <p className="text-sm text-foreground">
        Horas pico de respuesta: <span className="font-semibold">{hours}</span>
      </p>
    );
  }

  if (pattern_type === "avg_close_days") {
    return (
      <p className="text-sm text-foreground">
        Tiempo promedio de cierre:{" "}
        <span className="font-semibold">{String(pattern_data.avg_days ?? "—")} días</span>
      </p>
    );
  }

  if (pattern_type === "top_objections") {
    const reasons = Array.isArray(pattern_data.top_reasons)
      ? (pattern_data.top_reasons as Array<{ reason: string; count: number }>)
      : [];
    return (
      <div>
        <p className="text-sm text-foreground mb-1.5">Objeciones más comunes:</p>
        <ul className="flex flex-col gap-1">
          {reasons.map((r, i) => (
            <li key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="h-1 w-1 rounded-full bg-primary/50 shrink-0" />
              <span className="font-medium text-foreground">{r.reason}</span>
              <span>({r.count} casos)</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  // fallback for unknown pattern types
  return (
    <div className="text-sm text-muted-foreground">
      <span className="font-medium text-foreground">{pattern_type}</span>
      <pre className="mt-1 text-xs whitespace-pre-wrap break-all">
        {JSON.stringify(pattern_data, null, 2)}
      </pre>
    </div>
  );
}

const PATTERN_LABELS: Record<string, string> = {
  best_followup_day: "Seguimiento",
  peak_response_hours: "Horas pico",
  avg_close_days: "Ciclo de venta",
  top_objections: "Objeciones",
};

export function AIPatternsCard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai-patterns"],
    queryFn: () => api.getAiPatterns(),
    staleTime: 5 * 60_000,
    retry: false,
  });

  if (isLoading || isError || !data || data.length === 0) return null;

  return (
    <div className="rounded-xl border border-border bg-card shadow-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp className="h-4 w-4 text-primary shrink-0" />
        <div>
          <h3 className="font-semibold leading-tight">Patrones de tu negocio</h3>
          <p className="text-xs text-muted-foreground">Detectados por Walix AI sobre tu historial</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {data.map((pattern) => (
          <div
            key={pattern.pattern_type}
            className={cn(
              "rounded-lg border border-border bg-muted/30 p-3.5 flex flex-col gap-2",
            )}
          >
            <span className="text-[11px] font-semibold uppercase tracking-wide text-primary">
              {PATTERN_LABELS[pattern.pattern_type] ?? pattern.pattern_type}
            </span>

            <PatternContent pattern={pattern} />

            <div className="flex items-center gap-2 mt-auto pt-2 border-t border-border/60">
              <span className="text-[11px] text-muted-foreground">
                {Math.round(pattern.confidence_score * 100)}% confianza
              </span>
              <span className="text-[11px] text-muted-foreground">·</span>
              <span className="text-[11px] text-muted-foreground">
                sobre {pattern.sample_size} casos
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
