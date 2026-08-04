import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { useDashboardKpis } from "@/lib/queries/dashboard";
import { Sparkles, AlertTriangle, X, Settings2 } from "lucide-react";
import { LayoutRenderer } from "@/components/dashboard/LayoutRenderer";
import { CustomizeSheet } from "@/components/dashboard/CustomizeSheet";

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Buenos días";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

export default function Dashboard() {
  const { user } = useAuth();
  const [showAlert, setShowAlert] = useState(true);
  const [customizeOpen, setCustomizeOpen] = useState(false);

  const { data: kpis } = useDashboardKpis();
  const atRiskDealsCount = kpis?.staleDeals ?? 0;

  const displayName =
    (user as any)?.full_name ??
    (user as any)?.name ??
    user?.email?.split("@")[0] ??
    "ahí";
  const name = displayName.split(" ")[0];
  const today = new Date().toLocaleDateString("es-MX", {
    weekday: "long", day: "numeric", month: "long",
  });

  return (
    <div className="space-y-6 max-w-[1400px]">
      {/* Risk alert — chrome fijo, no configurable */}
      {showAlert && atRiskDealsCount > 0 && (
        <div className="flex items-center gap-3 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm">
          <AlertTriangle className="h-5 w-5 text-warning shrink-0" />
          <div className="flex-1 text-foreground">
            <strong>{atRiskDealsCount} oportunidades</strong> llevan más de 10 días sin actividad.{" "}
            <a href="/pipeline" className="font-medium text-warning underline-offset-2 hover:underline">
              Ver oportunidades →
            </a>
          </div>
          <button
            onClick={() => setShowAlert(false)}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Cerrar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Header — chrome fijo, no configurable */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight">
            {getGreeting()}, {name} 👋
          </h1>
          <p className="text-sm text-muted-foreground capitalize mt-1">{today}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setCustomizeOpen(true)}
            className="gap-2"
          >
            <Settings2 className="h-4 w-4" />
            Personalizar
          </Button>
          <Button
            onClick={() => { /* TODO fase 2 */ }}
            className="bg-gradient-brand hover:opacity-90 text-primary-foreground shadow-glow gap-2"
          >
            <Sparkles className="h-4 w-4" />
            Resumen del día
          </Button>
        </div>
      </div>

      {/* Widgets dinámicos — orden y visibilidad desde el backend */}
      <LayoutRenderer surface="dashboard" />

      <CustomizeSheet
        open={customizeOpen}
        onOpenChange={setCustomizeOpen}
        scope="user"
      />
    </div>
  );
}
