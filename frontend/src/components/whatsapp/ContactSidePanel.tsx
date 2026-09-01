import { useQuery } from "@tanstack/react-query";
import { ScrollArea } from "@/components/ui/scroll-area";
import { StatusBadge } from "./StatusBadge";
import { api, type LeadDetail } from "@/lib/api";
import { WBadge } from "@/components/walix/Badge";
import { AssignmentDropdown } from "./AssignmentDropdown";
import { cn } from "@/lib/utils";
import type { ServiceWindow, WindowTone } from "@/lib/whatsapp/serviceWindow";
import type { GuidanceCard } from "@/lib/whatsapp/guidance";

// Fallback mientras carga /qualification-config o si falla — coincide con el
// esquema "salud" para no dejar el panel en blanco (la clínica es el tenant
// con más tráfico); una vez resuelve la query, se reemplaza por los campos
// reales del branch.
const FALLBACK_QUAL_FIELDS = [
  { key: "parent_name", label: "Nombre del padre/tutor" },
  { key: "child_age", label: "Edad del niño" },
  { key: "consultation_reason", label: "Motivo de consulta" },
  { key: "parent_city", label: "Ciudad" },
];

const WINDOW_BADGE: Record<WindowTone, { bg: string; text: string; label: string }> = {
  open:    { bg: "bg-success/10",  text: "text-success",  label: "Abierta" },
  closing: { bg: "bg-warning/10",  text: "text-warning",  label: "Cerrándose" },
  closed:  { bg: "bg-danger/10",   text: "text-danger",   label: "Cerrada" },
};

const SENTIMENT_LABELS: Record<string, string> = {
  neutral: "Neutral",
  interesado: "Interesado",
  urgente: "Urgente",
  negativo: "Negativo",
};

const SENTIMENT_VARIANT: Record<string, "neutral" | "info" | "danger" | "warning"> = {
  neutral: "neutral",
  interesado: "info",
  urgente: "danger",
  negativo: "warning",
};

interface Props {
  lead: LeadDetail;
  serviceWindow?: ServiceWindow;
  guidance?: GuidanceCard;
}

export function ContactSidePanel({ lead, serviceWindow, guidance }: Props) {
  const qData = lead.qualification_data as Record<string, unknown>;

  const { data: qualConfig } = useQuery({
    queryKey: ["qualification-config", lead.branch_id],
    queryFn: () => api.getQualificationConfig(lead.branch_id),
    staleTime: 5 * 60 * 1000,
  });

  const qualFields = qualConfig?.required_fields ?? FALLBACK_QUAL_FIELDS;

  const score = lead.qualification_score;

  return (
    <aside className="w-[300px] shrink-0 border-l border-border bg-card hidden lg:flex flex-col h-full">
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-5">
          {/* Ventana de servicio 24 h */}
          {serviceWindow && (
            <section>
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Ventana WhatsApp
              </h3>
              <div className="border border-border rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Estado</span>
                  <span
                    className={cn(
                      "text-[10px] font-semibold px-2 py-0.5 rounded-full",
                      WINDOW_BADGE[serviceWindow.tone].bg,
                      WINDOW_BADGE[serviceWindow.tone].text,
                    )}
                  >
                    {WINDOW_BADGE[serviceWindow.tone].label}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{serviceWindow.description}</p>

                {guidance && (
                  <div className="pt-1 border-t border-border space-y-1.5">
                    <p className="text-xs font-medium">{guidance.title}</p>
                    <ul className="space-y-1">
                      {guidance.steps.map((step, i) => (
                        <li key={i} className="text-[11px] text-muted-foreground flex gap-1.5">
                          <span className="shrink-0 text-muted-foreground/50">{i + 1}.</span>
                          {step}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Calificacion */}
          <section>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              Calificacion
            </h3>
            <div className="border border-border rounded-lg p-3 space-y-3">
              {score != null && (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-muted-foreground">Score</span>
                    <span className="text-xs font-bold">{(score * 10).toFixed(1)}/10</span>
                  </div>
                  <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all"
                      style={{ width: `${score * 100}%` }}
                    />
                  </div>
                </div>
              )}
              <div className="flex items-center gap-2">
                <StatusBadge status={lead.status} />
                <WBadge variant={SENTIMENT_VARIANT[lead.sentiment] ?? "neutral"}>
                  {SENTIMENT_LABELS[lead.sentiment] ?? lead.sentiment}
                </WBadge>
              </div>
            </div>
          </section>

          {/* Datos de calificacion */}
          {Object.keys(qData).length > 0 && (
            <section>
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Datos del lead
              </h3>
              <div className="border border-border rounded-lg divide-y divide-border">
                {qualFields.map(({ key, label }) =>
                  qData[key] != null ? (
                    <div key={key} className="px-3 py-2">
                      <div className="text-[10px] text-muted-foreground">{label}</div>
                      <div className="text-xs font-medium mt-0.5">{String(qData[key])}</div>
                    </div>
                  ) : null
                )}
                {/* Render any extra fields not in our known list */}
                {Object.entries(qData)
                  .filter(([k]) => !qualFields.some((f) => f.key === k))
                  .map(([k, v]) => (
                    <div key={k} className="px-3 py-2">
                      <div className="text-[10px] text-muted-foreground">{k}</div>
                      <div className="text-xs font-medium mt-0.5">{String(v)}</div>
                    </div>
                  ))}
              </div>
            </section>
          )}

          {/* Asignacion */}
          <section>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              Asignacion
            </h3>
            <AssignmentDropdown lead={lead} roleLabel={qualConfig?.agent_role_label} />
          </section>

          {/* Info del lead */}
          <section>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              Lead
            </h3>
            <div className="border border-border rounded-lg divide-y divide-border">
              <div className="px-3 py-2">
                <div className="text-[10px] text-muted-foreground">Telefono WhatsApp</div>
                <div className="text-xs font-medium mt-0.5">{lead.wa_phone}</div>
              </div>
              {lead.contact_phone && (
                <div className="px-3 py-2">
                  <div className="text-[10px] text-muted-foreground">Telefono contacto</div>
                  <div className="text-xs font-medium mt-0.5">{lead.contact_phone}</div>
                </div>
              )}
              <div className="px-3 py-2">
                <div className="text-[10px] text-muted-foreground">Fuente</div>
                <div className="text-xs font-medium mt-0.5">{lead.source}</div>
              </div>
              {lead.assigned_to_name && (
                <div className="px-3 py-2">
                  <div className="text-[10px] text-muted-foreground">Asignado a</div>
                  <div className="text-xs font-medium mt-0.5">{lead.assigned_to_name}</div>
                </div>
              )}
              <div className="px-3 py-2">
                <div className="text-[10px] text-muted-foreground">Creado</div>
                <div className="text-xs font-medium mt-0.5">
                  {new Date(lead.created_at).toLocaleString("es-MX", {
                    day: "2-digit",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
              </div>
            </div>
          </section>
        </div>
      </ScrollArea>
    </aside>
  );
}
