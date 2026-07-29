import { useAuthStore } from "@/stores/auth";

export interface ContactStatus {
  key: string;
  label: string;
  color: string;
}

export function useTenantLabels() {
  const { entityName, entityPlural, contactStatuses, dealName, dealPlural } = useAuthStore();

  // Singular y plural con fallbacks seguros
  const entity = entityName || "Contacto";
  const entities = entityPlural || "Contactos";

  // Acciones contextuales — contactos
  const newEntityLabel = `Nuevo ${entity}`;                    // "Nuevo Paciente"
  const addEntityLabel = `Agregar ${entity}`;                  // "Agregar Alumno"
  const searchEntityPlaceholder = `Buscar ${entities}...`;     // "Buscar Pacientes..."
  const emptyStateLabel = `No hay ${entities} aún`;            // "No hay Alumnos aún"
  const totalLabel = (n: number) =>
    `${n} ${n === 1 ? entity : entities}`;                     // "1 Paciente" / "3 Pacientes"

  // Deals — configurable vía deal_name/deal_plural del tenant (TODO backend)
  const deal = dealName || "Oportunidad";
  const deals = dealPlural || "Oportunidades";
  const newDealLabel = `Nueva ${deal}`;                        // "Nueva Oportunidad"
  const addDealLabel = `Agregar ${deal}`;                      // "Agregar Oportunidad"

  // Estados del contacto — vienen de contact_statuses_config del tenant.
  // El fallback usa los DB LeadStatus keys (nuevo, calificado, etc.) para que
  // getStatusLabel/Color funcione sin configuración de template.
  const statuses: ContactStatus[] = contactStatuses?.length
    ? contactStatuses
    : [
        { key: "nuevo",           label: "Nuevo",           color: "#6366F1" },
        { key: "en_calificacion", label: "En calificación", color: "#3B82F6" },
        { key: "calificado",      label: "Calificado",      color: "#F59E0B" },
        { key: "escalado",        label: "Escalado",        color: "#EF4444" },
        { key: "perdido",         label: "Perdido",         color: "#9CA3AF" },
      ];

  const getStatusLabel = (key: string): string =>
    statuses.find((s) => s.key === key)?.label ?? key;

  const getStatusColor = (key: string): string =>
    statuses.find((s) => s.key === key)?.color ?? "#6B7280";

  return {
    entity,
    entities,
    newEntityLabel,
    addEntityLabel,
    searchEntityPlaceholder,
    emptyStateLabel,
    totalLabel,
    deal,
    deals,
    newDealLabel,
    addDealLabel,
    statuses,
    getStatusLabel,
    getStatusColor,
  };
}
