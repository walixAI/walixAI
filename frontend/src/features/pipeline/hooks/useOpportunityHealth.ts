import { useMemo } from "react";

export type HealthStatus = "activo" | "frio" | "estancado" | "vencido";

export interface HealthBadge {
  status: HealthStatus;
  label: string;
  colorClass: string; // Tailwind classes for badge
  icon: string;
}

interface Params {
  close_date: string | null;
  stage_entered_at: string;
  last_activity_at: string | null;
  status: string;
}

function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
}

function isPast(iso: string): boolean {
  return new Date(iso).getTime() < Date.now();
}

export function useOpportunityHealth(opp: Params): HealthBadge {
  return useMemo(() => {
    const isOpen = opp.status === "open";

    // 1. Vencido: close_date in the past + open
    if (isOpen && opp.close_date && isPast(opp.close_date)) {
      return {
        status: "vencido",
        label: "Vencido",
        colorClass: "bg-danger/10 text-danger border border-danger/20",
        icon: "🔴",
      };
    }

    // 2. Estancado: stuck in same stage > 14 days
    if (isOpen && daysSince(opp.stage_entered_at) > 14) {
      return {
        status: "estancado",
        label: "Estancado",
        colorClass: "bg-warning/10 text-warning border border-warning/20",
        icon: "⚠️",
      };
    }

    // 3. Frío: no activity > 5 days
    if (
      isOpen &&
      (!opp.last_activity_at || daysSince(opp.last_activity_at) > 5)
    ) {
      return {
        status: "frio",
        label: "Frío",
        colorClass: "bg-muted text-muted-foreground border border-border",
        icon: "❄️",
      };
    }

    // 4. Activo: default
    return {
      status: "activo",
      label: "Activo",
      colorClass: "bg-success/10 text-success border border-success/20",
      icon: "🔥",
    };
  }, [opp.close_date, opp.stage_entered_at, opp.last_activity_at, opp.status]);
}
