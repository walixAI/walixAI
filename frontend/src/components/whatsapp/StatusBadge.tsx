import { cn } from "@/lib/utils";
import type { LeadStatus } from "@/lib/api";

const STYLES: Record<LeadStatus, string> = {
  nuevo: "bg-info/10 text-info border-info/20",
  en_calificacion: "bg-warning/10 text-warning border-warning/20",
  calificado: "bg-success/10 text-success border-success/20",
  escalado: "bg-primary/10 text-primary border-primary/20",
  perdido: "bg-muted text-muted-foreground border-border",
};

const LABELS: Record<LeadStatus, string> = {
  nuevo: "Nuevo",
  en_calificacion: "En calificacion",
  calificado: "Calificado",
  escalado: "Escalado",
  perdido: "Perdido",
};

export function StatusBadge({ status, className }: { status: LeadStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border",
        STYLES[status],
        className
      )}
    >
      {LABELS[status]}
    </span>
  );
}
