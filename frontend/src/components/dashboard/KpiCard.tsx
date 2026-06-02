import { ArrowUp, ArrowDown } from "lucide-react";

interface KpiCardProps {
  label: string;
  value: string | number;
  delta_pct?: number | null;
  format?: "number" | "percent" | "seconds" | "currency";
  icon?: React.ReactNode;
  className?: string;
}

function formatValue(value: string | number, format?: string): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(n)) return String(value);
  switch (format) {
    case "percent":
      return `${n.toFixed(1)}%`;
    case "seconds": {
      if (n <= 0) return "—";
      if (n < 60) return `${Math.round(n)}s`;
      const mins = Math.floor(n / 60);
      const secs = Math.round(n % 60);
      return secs ? `${mins}m ${secs}s` : `${mins}m`;
    }
    case "currency":
      return `$${n.toLocaleString("es-MX")}`;
    default:
      return n.toLocaleString("es-MX");
  }
}

export function KpiCard({ label, value, delta_pct, format, icon, className = "" }: KpiCardProps) {
  const isPositive = delta_pct != null && delta_pct >= 0;

  return (
    <div className={`rounded-xl border border-border bg-card p-5 shadow-card hover:shadow-card-hover transition-all ${className}`}>
      <div className="flex items-start justify-between mb-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</p>
        {icon && <div className="text-muted-foreground/50">{icon}</div>}
      </div>

      <div className="font-syne text-[2rem] font-bold tracking-tight text-foreground leading-none mt-3">
        {formatValue(value, format)}
      </div>

      {delta_pct != null && (
        <div className={`flex items-center gap-0.5 mt-2.5 text-xs font-semibold ${isPositive ? "text-success" : "text-danger"}`}>
          {isPositive
            ? <ArrowUp className="h-3 w-3" />
            : <ArrowDown className="h-3 w-3" />}
          <span>{Math.abs(delta_pct).toFixed(1)}% vs período anterior</span>
        </div>
      )}
    </div>
  );
}
