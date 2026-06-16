import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, Check, ExternalLink, RefreshCcw, AlertCircle } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

const PLAN_LABELS: Record<string, string> = {
  trial: "Prueba gratuita",
  starter: "Starter",
  growth: "Growth",
  business: "Business",
};

const FAQ = [
  {
    q: "¿Puedo cambiar de plan?",
    a: "Sí. Puedes actualizar o reducir tu plan en cualquier momento. El cambio aplica al inicio del siguiente ciclo de facturación.",
  },
  {
    q: "¿Qué pasa con mis datos si cancelo?",
    a: "Tus datos permanecen en Walix por 30 días después de la cancelación. Durante ese período puedes reactivar tu plan sin perder nada.",
  },
  {
    q: "¿Emiten facturas?",
    a: "Sí. Recibirás una factura por correo electrónico en cada cobro. También puedes descargarlas desde el portal de facturación.",
  },
  {
    q: "¿Cuáles son los métodos de pago?",
    a: "Aceptamos tarjetas de crédito y débito (Visa, Mastercard, American Express). El cobro es en MXN.",
  },
];

export default function BillingPage() {
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  const { data: plans = [], isLoading: plansLoading } = useQuery({
    queryKey: ["billing-plans"],
    queryFn: () => api.getBillingPlans(),
  });

  const { data: sub, isLoading: subLoading, refetch: refetchSub } = useQuery({
    queryKey: ["billing-subscription"],
    queryFn: () => api.getBillingSubscription(),
    retry: 1,
  });

  const portalMutation = useMutation({
    mutationFn: () => api.getBillingPortal(),
    onSuccess: ({ portal_url }) => { window.location.href = portal_url; },
    onError: () => toast.error("No se pudo abrir el portal de facturación"),
  });

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelSubscription(),
    onSuccess: ({ message }) => { toast.success(message); refetchSub(); },
    onError: () => toast.error("No se pudo cancelar la suscripción"),
  });

  const reactivateMutation = useMutation({
    mutationFn: () => api.reactivateSubscription(),
    onSuccess: ({ message }) => { toast.success(message); refetchSub(); },
    onError: () => toast.error("No se pudo reactivar la suscripción"),
  });

  const handleCheckout = async (planKey: string) => {
    setCheckoutLoading(planKey);
    try {
      const { checkout_url } = await api.createCheckoutSession(planKey);
      window.location.href = checkout_url;
    } catch {
      toast.error("No se pudo iniciar el proceso de pago");
      setCheckoutLoading(null);
    }
  };

  const currentPlan = sub?.plan ?? "trial";
  const isTrial = currentPlan === "trial";

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-16">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Planes y facturación</h1>
        <p className="text-muted-foreground mt-1">
          Administra tu suscripción y método de pago.
        </p>
      </div>

      {/* ── Sección 1: Estado actual ── */}
      {!subLoading && sub && !isTrial && (
        <div className="rounded-xl border border-border bg-card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Plan actual</p>
              <p className="text-xl font-semibold">{PLAN_LABELS[currentPlan] ?? currentPlan}</p>
              {sub.current_period_end && (
                <p className="text-sm text-muted-foreground mt-0.5">
                  {sub.cancel_at_period_end
                    ? `Cancela el ${new Date(sub.current_period_end).toLocaleDateString("es-MX")}`
                    : `Renueva el ${new Date(sub.current_period_end).toLocaleDateString("es-MX")} · ${sub.days_until_renewal} días`}
                </p>
              )}
            </div>
            <Badge variant={sub.status === "active" ? "default" : "secondary"}>
              {sub.status}
            </Badge>
          </div>

          <div className="flex gap-3 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              onClick={() => portalMutation.mutate()}
              disabled={portalMutation.isPending}
            >
              {portalMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <ExternalLink className="h-4 w-4 mr-2" />
              )}
              Gestionar pago
            </Button>

            {sub.cancel_at_period_end ? (
              <Button
                variant="default"
                size="sm"
                onClick={() => reactivateMutation.mutate()}
                disabled={reactivateMutation.isPending}
              >
                {reactivateMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <RefreshCcw className="h-4 w-4 mr-2" />
                )}
                Reactivar suscripción
              </Button>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
              >
                Cancelar al final del período
              </Button>
            )}
          </div>

          {sub.cancel_at_period_end && sub.current_period_end && (
            <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              Tu plan cancela el {new Date(sub.current_period_end).toLocaleDateString("es-MX")}.
              Reactívalo para mantener el acceso.
            </div>
          )}
        </div>
      )}

      {/* ── Sección 2: Planes ── */}
      <div>
        <h2 className="text-lg font-semibold mb-4">
          {isTrial ? "Elige un plan para continuar" : "Cambiar plan"}
        </h2>

        {plansLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="grid md:grid-cols-3 gap-4">
            {plans.map((plan) => {
              const isCurrentPlan = plan.key === currentPlan;
              const isLoading = checkoutLoading === plan.key;

              return (
                <div
                  key={plan.key}
                  className={`relative rounded-xl border p-5 flex flex-col gap-4 transition-shadow ${
                    plan.highlighted
                      ? "border-primary shadow-lg shadow-primary/10"
                      : "border-border"
                  }`}
                >
                  {plan.highlighted && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-primary-foreground text-[10px] font-semibold px-2.5 py-0.5 rounded-full">
                      Recomendado
                    </span>
                  )}
                  {isCurrentPlan && (
                    <span className="absolute -top-3 right-4 bg-secondary text-secondary-foreground text-[10px] font-semibold px-2.5 py-0.5 rounded-full">
                      Plan actual
                    </span>
                  )}

                  <div>
                    <h3 className="font-semibold text-base">{plan.name}</h3>
                    <p className="text-2xl font-bold mt-1">
                      ${plan.price_mxn.toLocaleString("es-MX")}
                      <span className="text-sm font-normal text-muted-foreground"> /mes MXN</span>
                    </p>
                  </div>

                  <ul className="space-y-1.5 flex-1">
                    {plan.features.map((f) => (
                      <li key={f} className="flex items-center gap-2 text-sm">
                        <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                        {f}
                      </li>
                    ))}
                  </ul>

                  <Button
                    className="w-full"
                    variant={plan.highlighted ? "default" : "outline"}
                    disabled={isCurrentPlan || isLoading || !!checkoutLoading}
                    onClick={() => handleCheckout(plan.key)}
                  >
                    {isLoading ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : null}
                    {isCurrentPlan ? "Plan actual" : "Seleccionar"}
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Sección 3: FAQ ── */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Preguntas frecuentes</h2>
        <Accordion type="single" collapsible className="rounded-xl border border-border divide-y">
          {FAQ.map((item, i) => (
            <AccordionItem key={i} value={`faq-${i}`} className="px-4">
              <AccordionTrigger className="text-sm font-medium text-left">
                {item.q}
              </AccordionTrigger>
              <AccordionContent className="text-sm text-muted-foreground">
                {item.a}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </div>
  );
}
