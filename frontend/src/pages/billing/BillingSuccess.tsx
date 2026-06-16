import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Loader2 } from "lucide-react";

const PLAN_LABELS: Record<string, string> = {
  starter: "Starter",
  growth: "Growth",
  business: "Business",
};

const MAX_RETRIES = 5;
const RETRY_DELAY_MS = 1500;

export default function BillingSuccess() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("session_id");

  const [plan, setPlan] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retries, setRetries] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const pollPlan = async (attempt: number): Promise<void> => {
      if (cancelled) return;
      try {
        const sub = await api.getBillingSubscription();
        if (cancelled) return;

        if (sub.plan !== "trial") {
          setPlan(sub.plan);
          setLoading(false);
          return;
        }
      } catch {
        // keep retrying
      }

      if (attempt < MAX_RETRIES) {
        setRetries(attempt + 1);
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
        return pollPlan(attempt + 1);
      }

      // After max retries, show success anyway (webhook may lag)
      if (!cancelled) {
        setPlan("tu nuevo plan");
        setLoading(false);
      }
    };

    pollPlan(0);
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center px-4 gap-6">
      {loading ? (
        <>
          <Loader2 className="h-10 w-10 animate-spin text-primary" />
          <div>
            <p className="font-medium">Confirmando tu suscripción…</p>
            <p className="text-sm text-muted-foreground mt-1">
              {retries > 0 ? `Verificando… (intento ${retries}/${MAX_RETRIES})` : "Un momento por favor."}
            </p>
          </div>
        </>
      ) : (
        <>
          <div className="h-20 w-20 rounded-full bg-primary/10 grid place-items-center">
            <CheckCircle2 className="h-10 w-10 text-primary" />
          </div>
          <div className="space-y-2">
            <h1 className="text-2xl font-bold tracking-tight">
              ¡Bienvenido al plan {PLAN_LABELS[plan ?? ""] ?? plan}!
            </h1>
            <p className="text-muted-foreground max-w-sm mx-auto">
              Tu workspace está activo. Ya puedes usar todas las funcionalidades de tu plan.
            </p>
            {sessionId && (
              <p className="text-xs text-muted-foreground">
                ID de sesión: {sessionId.slice(0, 20)}…
              </p>
            )}
          </div>
          <Button
            size="lg"
            className="bg-gradient-brand hover:opacity-90"
            onClick={() => navigate("/dashboard")}
          >
            Ir al Dashboard →
          </Button>
        </>
      )}
    </div>
  );
}
