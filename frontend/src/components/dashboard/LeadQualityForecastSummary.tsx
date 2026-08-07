import { Link } from "react-router-dom";
import { TrendingUp, AlertTriangle, ArrowRight } from "lucide-react";
import { useForecastSummary } from "@/lib/queries/metrics";

export function LeadQualityForecastSummary() {
  const { data, isLoading } = useForecastSummary();

  const forecast = data?.pipeline_forecast ?? { high: 0, medium: 0, low: 0 };
  const atRiskCount = data?.at_risk_leads.length ?? 0;

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 grid place-items-center rounded-lg bg-primary/10 text-primary">
            <TrendingUp className="h-4 w-4" />
          </div>
          <h3 className="text-sm font-semibold">Forecast de calidad de leads</h3>
        </div>
        <Link
          to="/forecast"
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Ver forecast completo <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      {isLoading || !data ? (
        <div className="grid grid-cols-3 gap-3 mb-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="rounded-lg border border-success/30 bg-success/5 px-3 py-2.5 text-center">
              <p className="text-xs text-muted-foreground">Alta prob.</p>
              <p className="mt-1 text-2xl font-bold text-success">{forecast.high}</p>
            </div>
            <div className="rounded-lg border border-warning/30 bg-warning/5 px-3 py-2.5 text-center">
              <p className="text-xs text-muted-foreground">Media</p>
              <p className="mt-1 text-2xl font-bold text-warning">{forecast.medium}</p>
            </div>
            <div className="rounded-lg border border-border px-3 py-2.5 text-center">
              <p className="text-xs text-muted-foreground">Baja</p>
              <p className="mt-1 text-2xl font-bold text-muted-foreground">{forecast.low}</p>
            </div>
          </div>

          {atRiskCount > 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>
                <strong>{atRiskCount}</strong> lead{atRiskCount !== 1 ? "s" : ""} en riesgo de perderse
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
