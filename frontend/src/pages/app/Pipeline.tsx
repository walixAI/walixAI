import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Kanban, List } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type BoardLeadCard } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useAIBarStore } from "@/stores/aiBarStore";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { KanbanBoard } from "@/components/pipeline/KanbanBoard";
import { ListView } from "@/components/pipeline/ListView";
import { LeadDetailSheet } from "@/components/pipeline/LeadDetailSheet";

type ViewMode = "kanban" | "list";
const VIEW_KEY = "walix-pipeline-view";

export default function Pipeline() {
  const { user } = useAuth();
  const { setContext } = useAIBarStore();

  const [view, setView] = useState<ViewMode>(
    () => (localStorage.getItem(VIEW_KEY) as ViewMode | null) ?? "kanban",
  );

  const isMultiBranch = user?.role === "owner" || user?.role === "it";
  const [selectedBranchId, setSelectedBranchId] = useState<string>("");

  const { data: branches = [] } = useQuery({
    queryKey: ["branches"],
    queryFn: () => api.listBranches(),
    enabled: isMultiBranch,
  });

  const branchId: string =
    user?.branch_id ??
    (selectedBranchId || branches[0]?.id) ??
    "";

  // Advisor filter
  const [advisorId, setAdvisorId] = useState<string>("all");

  const { data: team = [] } = useQuery({
    queryKey: ["team", branchId],
    queryFn: () => api.getTeam(branchId),
    enabled: Boolean(branchId),
    staleTime: 2 * 60_000,
  });

  // Lead detail sheet
  const [selectedCard, setSelectedCard] = useState<{
    leadId: string;
    stageName: string;
    stageColor: string | null;
  } | null>(null);

  // Update AI bar context when screen/branch changes
  useEffect(() => {
    if (branchId) setContext({ screen: "pipeline", branch_id: branchId });
  }, [branchId, setContext]);

  const handleViewChange = (v: ViewMode) => {
    setView(v);
    localStorage.setItem(VIEW_KEY, v);
  };

  const handleLeadClick = (
    card: BoardLeadCard,
    stageName: string,
    stageColor: string | null,
  ) => {
    setSelectedCard({ leadId: card.id, stageName, stageColor });
  };

  const resolvedAdvisorId = advisorId === "all" ? null : advisorId;
  const branchName = isMultiBranch
    ? (branches.find((b) => b.id === branchId)?.name ?? "")
    : "";

  return (
    <div className="h-full flex flex-col gap-4">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 flex-wrap shrink-0">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Pipeline</h1>
          {branchName && (
            <p className="text-xs text-muted-foreground mt-0.5">{branchName}</p>
          )}
        </div>

        {/* View toggle */}
        <div className="flex items-center rounded-lg border border-border overflow-hidden ml-auto">
          <button
            onClick={() => handleViewChange("kanban")}
            className={cn(
              "p-2 transition-colors",
              view === "kanban"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-muted",
            )}
            aria-label="Vista kanban"
          >
            <Kanban className="h-4 w-4" />
          </button>
          <button
            onClick={() => handleViewChange("list")}
            className={cn(
              "p-2 transition-colors",
              view === "list"
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-muted",
            )}
            aria-label="Vista lista"
          >
            <List className="h-4 w-4" />
          </button>
        </div>

        {/* Branch selector (multi-branch roles only) */}
        {isMultiBranch && branches.length > 1 && (
          <Select value={branchId} onValueChange={setSelectedBranchId}>
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
        )}

        {/* Advisor filter */}
        {team.length > 1 && (
          <div className="flex items-center gap-2">
            <Label className="text-xs text-muted-foreground shrink-0">Asesor</Label>
            <Select value={advisorId} onValueChange={setAdvisorId}>
              <SelectTrigger className="h-8 w-40 text-xs">
                <SelectValue placeholder="Todos" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all" className="text-xs">
                  Todos
                </SelectItem>
                {team.map((member) => (
                  <SelectItem key={member.id} value={member.id} className="text-xs">
                    {member.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      {/* ── Content ────────────────────────────────────────────────────────── */}
      {!branchId ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-muted-foreground">
            Selecciona una sucursal para ver el pipeline.
          </p>
        </div>
      ) : view === "kanban" ? (
        <div className="flex-1 overflow-x-auto min-h-0">
          <KanbanBoard
            branchId={branchId}
            advisorId={resolvedAdvisorId}
            onLeadClick={handleLeadClick}
          />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto min-h-0">
          <ListView
            branchId={branchId}
            advisorId={resolvedAdvisorId}
            onLeadClick={handleLeadClick}
          />
        </div>
      )}

      {/* Lead detail sheet */}
      <LeadDetailSheet
        leadId={selectedCard?.leadId ?? null}
        stageName={selectedCard?.stageName}
        stageColor={selectedCard?.stageColor}
        onClose={() => setSelectedCard(null)}
      />
    </div>
  );
}
