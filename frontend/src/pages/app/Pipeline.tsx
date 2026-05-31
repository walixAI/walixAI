import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api, type LeadListItem, type PipelineStageOut } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { StatusBadge } from "@/components/whatsapp/StatusBadge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export default function Pipeline() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const isMultiBranch = user?.role === "owner" || user?.role === "it";
  const [selectedBranchId, setSelectedBranchId] = useState<string>("");

  const { data: branches = [] } = useQuery({
    queryKey: ["branches"],
    queryFn: () => api.listBranches(),
    enabled: isMultiBranch,
  });

  // branchId: explicit for multi-branch users, fixed for everyone else
  const resolvedBranchId = selectedBranchId || (branches[0]?.id ?? "");
  const branchId = user?.branch_id ?? resolvedBranchId;

  const { data: stages = [], isLoading: stagesLoading } = useQuery({
    queryKey: ["pipeline", branchId],
    queryFn: () => api.getBranchPipeline(branchId),
    enabled: !!branchId,
  });

  const { data: leadsData, isLoading: leadsLoading } = useQuery({
    queryKey: ["leads", "pipeline"],
    queryFn: () => api.listLeads({ all: true }),
    refetchInterval: 30_000,
  });

  const leads = leadsData?.items ?? [];

  // Group leads by pipeline_stage_id; null → first stage
  const leadsByStage = useMemo(() => {
    const map: Record<string, LeadListItem[]> = {};
    for (const s of stages) map[s.id] = [];

    const firstId = stages[0]?.id;
    for (const lead of leads) {
      const sid = lead.pipeline_stage_id ?? firstId;
      if (sid && sid in map) {
        map[sid].push(lead);
      }
    }
    return map;
  }, [stages, leads]);

  const isLoading = stagesLoading || leadsLoading;
  const branchName = isMultiBranch
    ? (branches.find((b) => b.id === branchId)?.name ?? "")
    : "";

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-6 pt-6 pb-4 flex items-center gap-4 shrink-0">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Pipeline</h1>
          {branchName && (
            <p className="text-xs text-muted-foreground mt-0.5">{branchName}</p>
          )}
        </div>

        {isMultiBranch && branches.length > 1 && (
          <div className="flex items-center gap-2 ml-auto">
            <Label className="text-xs text-muted-foreground shrink-0">Sucursal</Label>
            <Select
              value={branchId}
              onValueChange={setSelectedBranchId}
            >
              <SelectTrigger className="h-8 w-44 text-xs">
                <SelectValue placeholder="Selecciona sucursal" />
              </SelectTrigger>
              <SelectContent>
                {branches.map((b) => (
                  <SelectItem key={b.id} value={b.id} className="text-xs">
                    {b.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      {/* Board */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : !branchId ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-muted-foreground">Selecciona una sucursal para ver el pipeline.</p>
        </div>
      ) : stages.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-muted-foreground">Esta sucursal no tiene etapas de pipeline configuradas.</p>
        </div>
      ) : (
        <div className="flex-1 overflow-x-auto px-6 pb-6">
          <div className="flex gap-3 h-full" style={{ minWidth: "max-content" }}>
            {stages.map((stage) => (
              <KanbanColumn
                key={stage.id}
                stage={stage}
                leads={leadsByStage[stage.id] ?? []}
                onLeadClick={(lead) => navigate(`/whatsapp?leadId=${lead.id}`)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Kanban column ──────────────────────────────────────────────────────────────

function KanbanColumn({
  stage,
  leads,
  onLeadClick,
}: {
  stage: PipelineStageOut;
  leads: LeadListItem[];
  onLeadClick: (lead: LeadListItem) => void;
}) {
  return (
    <div className="w-56 shrink-0 flex flex-col rounded-xl border border-border bg-card">
      {/* Column header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <span
          className="h-2.5 w-2.5 rounded-full shrink-0"
          style={{ backgroundColor: stage.color ?? "#888" }}
        />
        <span className="text-sm font-semibold truncate flex-1">{stage.name}</span>
        <span
          className={cn(
            "text-xs font-medium tabular-nums px-1.5 py-0.5 rounded-full",
            leads.length > 0
              ? "bg-primary/10 text-primary"
              : "bg-muted text-muted-foreground"
          )}
        >
          {leads.length}
        </span>
      </div>

      {/* Cards */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2 min-h-[120px]">
        {leads.length === 0 ? (
          <p className="text-[11px] text-muted-foreground text-center py-8 select-none">
            Sin leads
          </p>
        ) : (
          leads.map((lead) => (
            <LeadCard key={lead.id} lead={lead} onClick={() => onLeadClick(lead)} />
          ))
        )}
      </div>
    </div>
  );
}

// ── Lead card ──────────────────────────────────────────────────────────────────

function LeadCard({
  lead,
  onClick,
}: {
  lead: LeadListItem;
  onClick: () => void;
}) {
  const displayName = lead.name ?? lead.wa_phone;

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left rounded-lg border border-border bg-background px-3 py-2.5",
        "hover:border-primary/40 hover:shadow-sm transition-all duration-150"
      )}
    >
      <p className="text-sm font-medium truncate">{displayName}</p>
      <div className="flex items-center justify-between mt-1.5 gap-1">
        <StatusBadge status={lead.status} />
        {lead.qualification_score !== null && lead.qualification_score !== undefined && (
          <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
            {Math.round(lead.qualification_score * 100)}%
          </span>
        )}
      </div>
    </button>
  );
}
