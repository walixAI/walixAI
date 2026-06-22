import type { PipelineDeal } from "@/lib/queries/pipeline";

export type HealthSignal = "hot" | "cold" | "stale" | "overdue";

export interface HealthInfo {
  signals: HealthSignal[];
  daysInStage: number;
  daysSinceContactActivity: number | null;
  isOverdue: boolean;
}

const DAY_MS = 86_400_000;

export function computeDealHealth(
  deal: PipelineDeal,
  contactLastActivityAt: string | null | undefined,
): HealthInfo {
  const now = Date.now();
  const daysInStage = Math.max(0, Math.floor((now - new Date(deal.updatedAt).getTime()) / DAY_MS));

  const daysSinceContactActivity = contactLastActivityAt
    ? Math.max(0, Math.floor((now - new Date(contactLastActivityAt).getTime()) / DAY_MS))
    : null;

  const isOverdue =
    !!deal.expectedCloseDate &&
    !deal.isWon &&
    !deal.isLost &&
    new Date(deal.expectedCloseDate).getTime() < now;

  const signals: HealthSignal[] = [];
  if (deal.isWon || deal.isLost) {
    return { signals, daysInStage, daysSinceContactActivity, isOverdue: false };
  }

  if (daysSinceContactActivity !== null && daysSinceContactActivity < 1) signals.push("hot");
  else if (daysSinceContactActivity !== null && daysSinceContactActivity > 7) signals.push("cold");

  if (daysInStage > 14) signals.push("stale");
  if (isOverdue) signals.push("overdue");

  return { signals, daysInStage, daysSinceContactActivity, isOverdue };
}

export const HEALTH_META: Record<HealthSignal, { label: string; emoji: string; className: string; tooltip: (info: HealthInfo) => string }> = {
  hot: {
    label: "Hot",
    emoji: "🔥",
    className: "bg-success/15 text-success border-success/30",
    tooltip: () => "Actividad del contacto en las últimas 24 horas",
  },
  cold: {
    label: "Cold",
    emoji: "💤",
    className: "bg-muted text-muted-foreground border-border",
    tooltip: (i) => `Sin actividad del contacto hace ${i.daysSinceContactActivity ?? "?"} días`,
  },
  stale: {
    label: "Stale",
    emoji: "⚠️",
    className: "bg-warning/15 text-warning border-warning/30",
    tooltip: (i) => `${i.daysInStage} días sin movimiento en esta etapa`,
  },
  overdue: {
    label: "Overdue",
    emoji: "📅",
    className: "bg-danger/15 text-danger border-danger/30",
    tooltip: () => "Fecha estimada de cierre ya pasó",
  },
};
