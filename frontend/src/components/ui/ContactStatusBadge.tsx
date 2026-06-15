import type { LeadStatus } from "@/lib/queries/contacts";
import { useTenantLabels } from "@/hooks/useTenantLabels";

// Clases Tailwind por estado — usadas como fallback visual cuando no hay color del tenant
const STATUS_CONFIG: Record<LeadStatus, { label: string; className: string }> = {
  nuevo:          { label: "Nuevo",          className: "bg-indigo-100 text-indigo-700 border-indigo-200 dark:bg-indigo-900/30 dark:text-indigo-300" },
  en_calificacion:{ label: "En calificación",className: "bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-900/30 dark:text-sky-300" },
  calificado:     { label: "Calificado",     className: "bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300" },
  escalado:       { label: "Escalado",       className: "bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-300" },
  perdido:        { label: "Perdido",        className: "bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-400" },
};

interface ContactStatusBadgeProps {
  status: LeadStatus | string;
  size?: "sm" | "md";
}

export function ContactStatusBadge({ status, size = "sm" }: ContactStatusBadgeProps) {
  const { statuses } = useTenantLabels();

  const sizeClass = size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs";
  const base = `inline-flex items-center border rounded-full font-medium whitespace-nowrap ${sizeClass}`;

  // Buscar en los status del tenant (cubre tanto DB keys como template keys)
  const tenantStatus = statuses.find((s) => s.key === status);
  if (tenantStatus) {
    const c = tenantStatus.color;
    return (
      <span
        className={base}
        style={{ backgroundColor: `${c}20`, color: c, borderColor: `${c}50` }}
      >
        {tenantStatus.label}
      </span>
    );
  }

  // Fallback: Tailwind classes estáticas para LeadStatus DB values
  const cfg = STATUS_CONFIG[status as LeadStatus] ?? STATUS_CONFIG.nuevo;
  return (
    <span className={`${base} ${cfg.className}`}>
      {cfg.label}
    </span>
  );
}

export { STATUS_CONFIG };
