import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useTenantLabels } from "@/hooks/useTenantLabels";

// ── Persistence ───────────────────────────────────────────────────────────────

const tourKey = (userId: string) => `walix.tour.completed.v1.${userId}`;

export function hasCompletedTour(userId: string): boolean {
  return localStorage.getItem(tourKey(userId)) === "true";
}

export function markTourCompleted(userId: string): void {
  localStorage.setItem(tourKey(userId), "true");
}

export function resetTour(userId: string): void {
  localStorage.removeItem(tourKey(userId));
}

// ── Step definitions ──────────────────────────────────────────────────────────

type Placement = "right" | "bottom" | "left" | "top" | "center";

interface TourStep {
  id: string;
  target: string | null;
  title: string;
  description: string;
  placement: Placement;
}

function useTourSteps(): TourStep[] {
  const { deals, entities } = useTenantLabels();
  return [
    {
      id: "welcome",
      target: null,
      placement: "center",
      title: "Bienvenido a Walix",
      description: "Te guiaremos por las secciones principales en menos de un minuto.",
    },
    {
      id: "dashboard",
      target: "nav-dashboard",
      placement: "right",
      title: "Dashboard",
      description: "Tu vista general: actividad reciente, métricas y resumen del negocio de un vistazo.",
    },
    {
      id: "pipeline",
      target: "nav-pipeline",
      placement: "right",
      title: deals,
      description: `Gestiona tus ${deals.toLowerCase()} en un tablero Kanban. Arrastra entre etapas y lleva el seguimiento de cada cierre.`,
    },
    {
      id: "contacts",
      target: "nav-contacts",
      placement: "right",
      title: entities,
      description: `Toda la información de tus ${entities.toLowerCase()} en un solo lugar: historial, estado y próximas acciones.`,
    },
    {
      id: "whatsapp",
      target: "nav-whatsapp",
      placement: "right",
      title: "WhatsApp",
      description: "Conversaciones entrantes, handoff al equipo y contexto completo de cada contacto.",
    },
    {
      id: "ai-bar",
      target: "ai-prompt",
      placement: "bottom",
      title: "Walix AI",
      description: "Escribe instrucciones en lenguaje natural o presiona ⌘K para enfocar el campo. El AI bar actúa sobre el contexto de la pantalla actual.",
    },
    {
      id: "done",
      target: null,
      placement: "center",
      title: "¡Todo listo!",
      description: "Ya conoces lo esencial. Puedes reiniciar este tour en cualquier momento desde el menú de tu perfil (esquina superior derecha).",
    },
  ];
}

// ── Geometry ──────────────────────────────────────────────────────────────────

interface Rect { top: number; left: number; width: number; height: number }

const PAD = 8;

function getTargetRect(dataTour: string): Rect | null {
  const el = document.querySelector(`[data-tour="${dataTour}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

// ── OnboardingTour ────────────────────────────────────────────────────────────

const TOOLTIP_W = 320;

interface Props {
  open: boolean;
  onClose: () => void;
}

export function OnboardingTour({ open, onClose }: Props) {
  const [step, setStep] = useState(0);
  const [targetRect, setTargetRect] = useState<Rect | null>(null);
  const { user } = useAuth();
  const steps = useTourSteps();
  const current = steps[step];
  const isFirst = step === 0;
  const isLast = step === steps.length - 1;

  useEffect(() => {
    if (open) setStep(0);
  }, [open]);

  useEffect(() => {
    if (!open || !current?.target) { setTargetRect(null); return; }
    const update = () => setTargetRect(getTargetRect(current.target!));
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [open, current?.target, step]);

  function finish() {
    if (user?.id) markTourCompleted(user.id);
    onClose();
  }

  if (!open || !current) return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;

  const spot: Rect | null = targetRect
    ? { top: targetRect.top - PAD, left: targetRect.left - PAD, width: targetRect.width + PAD * 2, height: targetRect.height + PAD * 2 }
    : null;

  const maskPath = spot
    ? `M 0 0 H ${vw} V ${vh} H 0 Z M ${spot.left} ${spot.top} h ${spot.width} v ${spot.height} h -${spot.width} Z`
    : `M 0 0 H ${vw} V ${vh} H 0 Z`;

  function tooltipStyle(): React.CSSProperties {
    const GAP = 16;
    if (!spot || current.placement === "center") {
      return { position: "fixed", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: TOOLTIP_W };
    }
    if (current.placement === "right") {
      const left = Math.min(spot.left + spot.width + GAP, vw - TOOLTIP_W - 16);
      const top = Math.min(Math.max(spot.top, 16), vh - 220);
      return { position: "fixed", top, left, width: TOOLTIP_W };
    }
    if (current.placement === "bottom") {
      const top = Math.min(spot.top + spot.height + GAP, vh - 220);
      const left = Math.max(16, Math.min(spot.left, vw - TOOLTIP_W - 16));
      return { position: "fixed", top, left, width: TOOLTIP_W };
    }
    if (current.placement === "left") {
      const left = Math.max(16, spot.left - TOOLTIP_W - GAP);
      const top = Math.min(Math.max(spot.top, 16), vh - 220);
      return { position: "fixed", top, left, width: TOOLTIP_W };
    }
    if (current.placement === "top") {
      const top = Math.max(16, spot.top - 220 - GAP);
      const left = Math.max(16, Math.min(spot.left, vw - TOOLTIP_W - 16));
      return { position: "fixed", top, left, width: TOOLTIP_W };
    }
    return { position: "fixed", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: TOOLTIP_W };
  }

  return (
    <div className="fixed inset-0 z-[9999] pointer-events-none" role="dialog" aria-modal aria-label="Tour de bienvenida">
      {/* Overlay with spotlight cutout */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-auto"
        onClick={finish}
      >
        <path d={maskPath} fill="rgba(0,0,0,0.55)" fillRule="evenodd" />
        {spot && (
          <rect
            x={spot.left} y={spot.top}
            width={spot.width} height={spot.height}
            rx={8} fill="transparent"
            stroke="hsl(var(--primary))" strokeWidth={2}
          />
        )}
      </svg>

      {/* Tooltip */}
      <div
        className="pointer-events-auto bg-card border border-border rounded-xl shadow-xl p-5"
        style={tooltipStyle()}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Progress dots */}
        <div className="flex gap-1.5 mb-3">
          {steps.map((_, i) => (
            <div
              key={i}
              className={`h-1.5 rounded-full transition-all ${
                i === step ? "w-6 bg-primary" : "w-1.5 bg-muted-foreground/30"
              }`}
            />
          ))}
        </div>

        <h3 className="font-semibold text-base mb-1">{current.title}</h3>
        <p className="text-sm text-muted-foreground mb-4">{current.description}</p>

        <div className="flex items-center justify-between gap-2">
          <button
            onClick={finish}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Saltar tour
          </button>
          <div className="flex gap-2">
            {!isFirst && (
              <button
                onClick={() => setStep((s) => Math.max(0, s - 1))}
                className="px-3 py-1.5 text-sm rounded-md border border-border hover:bg-muted transition-colors"
              >
                Atrás
              </button>
            )}
            <button
              onClick={() => isLast ? finish() : setStep((s) => s + 1)}
              className="px-3 py-1.5 text-sm rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              {isLast ? "¡Listo!" : "Siguiente →"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── useAutoOnboardingTour ─────────────────────────────────────────────────────

export function useAutoOnboardingTour() {
  const [open, setOpen] = useState(false);
  const { user } = useAuth();

  useEffect(() => {
    if (!user?.id) return;
    if (hasCompletedTour(user.id)) return;
    const timer = setTimeout(() => setOpen(true), 600);
    return () => clearTimeout(timer);
  }, [user?.id]);

  const start = useCallback(() => setOpen(true), []);
  const close = useCallback(() => setOpen(false), []);

  return { open, start, close };
}
