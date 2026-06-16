import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Zap } from "lucide-react";

interface TrialStatus {
  plan: string;
  is_trial: boolean;
  trial_ends_at: string | null;
  days_remaining: number;
  trial_expired: boolean;
}

interface TrialBannerProps {
  onExpired?: () => void;
}

export function TrialBanner({ onExpired }: TrialBannerProps) {
  const [status, setStatus] = useState<TrialStatus | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.getTrialStatus().then(setStatus).catch(() => {});
  }, []);

  if (!status || !status.is_trial) return null;

  if (status.trial_expired) {
    onExpired?.();
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background/95 backdrop-blur-sm p-6">
        <div className="max-w-md text-center space-y-4">
          <div className="mx-auto grid place-items-center h-16 w-16 rounded-full bg-destructive/10">
            <AlertTriangle className="h-8 w-8 text-destructive" />
          </div>
          <h2 className="text-2xl font-bold tracking-tight">Tu período de prueba ha terminado</h2>
          <p className="text-muted-foreground">
            Activa un plan para continuar usando Walix y no perder tus datos.
          </p>
          <Button
            size="lg"
            className="bg-gradient-brand hover:opacity-90"
            onClick={() => navigate("/billing")}
          >
            <Zap className="h-4 w-4 mr-2" />
            Ver planes
          </Button>
        </div>
      </div>
    );
  }

  const urgent = status.days_remaining <= 3;

  return (
    <div
      className={
        urgent
          ? "flex items-center justify-between gap-3 px-4 py-2 text-sm bg-destructive text-destructive-foreground"
          : "flex items-center justify-between gap-3 px-4 py-2 text-sm bg-primary/10 text-primary border-b border-primary/20"
      }
    >
      <span className="flex items-center gap-2">
        {urgent ? (
          <AlertTriangle className="h-4 w-4 shrink-0" />
        ) : (
          <Zap className="h-4 w-4 shrink-0" />
        )}
        {urgent
          ? `⚠️ Tu prueba vence en ${status.days_remaining} día${status.days_remaining !== 1 ? "s" : ""} · Activa ahora`
          : `🎉 Tu prueba gratuita vence en ${status.days_remaining} días · Activa tu plan para no perder tus datos`}
      </span>
      <Button
        size="sm"
        variant={urgent ? "secondary" : "default"}
        className="shrink-0 h-7 text-xs"
        onClick={() => navigate("/billing")}
      >
        {urgent ? "Activar ahora" : "Activar plan"} →
      </Button>
    </div>
  );
}
