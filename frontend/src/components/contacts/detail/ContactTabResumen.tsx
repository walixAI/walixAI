import { useQuery } from "@tanstack/react-query";
import { api, type AgentSuggestion } from "@/lib/api";
import { LeadScoreGauge } from "@/components/leads/LeadScoreGauge";
import { AgentSuggestionCard } from "@/components/agents/AgentSuggestionCard";
import { ActivityTimelineItem } from "./ActivityTimelineItem";
import { Skeleton } from "@/components/ui/skeleton";
import type { ContactRow } from "@/lib/queries/contacts";
import type { ActivityRow } from "@/lib/queries/activities";

function KpiCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3 space-y-0.5">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">{label}</p>
      <p className="text-xl font-bold tabular-nums">{value}</p>
    </div>
  );
}

interface ContactTabResumenProps {
  contact: ContactRow;
  recentActivities: ActivityRow[];
  activitiesTotal: number;
  activitiesLoading: boolean;
  contactId: string;
  activitiesQueryKey: unknown[];
  onViewAllActivities: () => void;
}

export function ContactTabResumen({
  contact,
  recentActivities,
  activitiesTotal,
  activitiesLoading,
  contactId,
  activitiesQueryKey,
  onViewAllActivities,
}: ContactTabResumenProps) {
  const daysInPipeline = Math.floor(
    (Date.now() - new Date(contact.createdAt).getTime()) / 86_400_000,
  );

  const { data: allSuggestions = [] } = useQuery({
    queryKey: ["agent-suggestions"],
    queryFn: () => api.getAgentSuggestions(),
    staleTime: 60_000,
  });

  const contactSuggestions: AgentSuggestion[] = allSuggestions.filter(
    (s) =>
      s.status === "suggested" &&
      (s.action_payload?.lead_id as string | undefined) === contactId,
  );

  return (
    <div className="space-y-5">
      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KpiCard label="Días en pipeline" value={daysInPipeline} />
        <KpiCard label="Actividades" value={activitiesTotal} />
        <KpiCard label="Score" value={contact.currentScore ?? "—"} />
        <KpiCard label="Estado" value={contact.status} />
      </div>

      {/* Lead score gauge */}
      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
          Score de calificación
        </p>
        <LeadScoreGauge leadId={contactId} />
      </div>

      {/* Agent suggestions */}
      {contactSuggestions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Sugerencias IA
          </p>
          {contactSuggestions.map((s) => (
            <AgentSuggestionCard key={s.id} suggestion={s} compact />
          ))}
        </div>
      )}

      {/* Recent activities */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Actividad reciente
          </p>
          {activitiesTotal > 5 && (
            <button
              type="button"
              onClick={onViewAllActivities}
              className="text-xs text-primary hover:underline"
            >
              Ver todas ({activitiesTotal})
            </button>
          )}
        </div>

        {activitiesLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <Skeleton className="h-7 w-7 rounded-full shrink-0" />
                <div className="space-y-1.5 flex-1">
                  <Skeleton className="h-3 w-2/3" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              </div>
            ))}
          </div>
        ) : recentActivities.length === 0 ? (
          <p className="text-sm text-muted-foreground py-3">Sin actividades registradas.</p>
        ) : (
          <div className="space-y-0.5">
            {recentActivities.slice(0, 5).map((a) => (
              <ActivityTimelineItem
                key={a.id}
                activity={a}
                contactId={contactId}
                queryKey={activitiesQueryKey}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
