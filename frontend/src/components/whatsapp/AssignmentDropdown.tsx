import { useEffect, useRef, useState } from "react";
import { ChevronDown, Loader2, UserCheck } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type AgentOut, type LeadDetail } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ROLE_LABEL: Record<string, string> = {
  doctor: "Doctor",
  asesor: "Asesor",
  gerente: "Gerente",
  owner: "Owner",
  it: "IT",
};

const ROLE_COLOR: Record<string, string> = {
  doctor: "bg-emerald-100 text-emerald-700",
  asesor: "bg-yellow-100 text-yellow-700",
  gerente: "bg-slate-100 text-slate-600",
  owner: "bg-slate-100 text-slate-600",
  it: "bg-slate-100 text-slate-600",
};

function AgentAvatar({ name, role }: { name: string; role: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center w-7 h-7 rounded-full text-[11px] font-bold shrink-0",
        ROLE_COLOR[role] ?? "bg-slate-100 text-slate-600"
      )}
    >
      {name.charAt(0).toUpperCase()}
    </span>
  );
}

interface Props {
  lead: LeadDetail;
}

export function AssignmentDropdown({ lead }: Props) {
  const qc = useQueryClient();

  // Cached agents list — fetched once per component mount
  const [agents, setAgents] = useState<AgentOut[] | null>(null);
  const [loadingAgents, setLoadingAgents] = useState(false);

  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<AgentOut | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSelected(null);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  async function handleToggle() {
    if (open) {
      setOpen(false);
      setSelected(null);
      return;
    }
    // Fetch agents once; re-use cache on subsequent opens
    if (!agents) {
      setLoadingAgents(true);
      try {
        const data = await api.getBranchAgents(lead.branch_id);
        setAgents(data);
      } catch {
        toast.error("No se pudo cargar la lista de médicos");
        setLoadingAgents(false);
        return;
      }
      setLoadingAgents(false);
    }
    setOpen(true);
  }

  const assignMutation = useMutation({
    mutationFn: (agentId: string) => api.assignLead(lead.id, agentId),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ["lead", lead.id] });
      qc.invalidateQueries({ queryKey: ["leads", "whatsapp"] });
      setOpen(false);
      setSelected(null);
      toast.success(`Lead asignado a ${updated.assigned_to_name ?? "el médico"}`);
    },
    onError: (e: Error) => toast.error("Error al asignar", { description: e.message }),
  });

  const isAssigned = !!lead.assigned_to_name;
  const buttonLabel = loadingAgents
    ? ""
    : isAssigned
    ? "Reasignar"
    : "Asignar al médico";

  return (
    <div ref={containerRef} className="relative">
      {/* Current assignment display */}
      {isAssigned && (
        <div className="flex items-center gap-1.5 mb-2">
          <UserCheck className="h-3.5 w-3.5 text-emerald-600 shrink-0" />
          <span className="text-xs text-foreground font-medium truncate">
            {lead.assigned_to_name}
          </span>
        </div>
      )}

      {/* Toggle button */}
      <Button
        variant="outline"
        size="sm"
        className="w-full justify-between text-xs h-8"
        onClick={handleToggle}
        disabled={assignMutation.isPending}
      >
        <span>{buttonLabel}</span>
        {loadingAgents ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
        )}
      </Button>

      {/* Dropdown */}
      {open && agents && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-card shadow-lg">
          {/* Confirmation step */}
          {selected ? (
            <div className="p-3 space-y-2">
              <p className="text-xs text-center text-foreground font-medium">
                ¿Asignar a {selected.name}?
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  className="flex-1 h-7 text-xs"
                  onClick={() => assignMutation.mutate(selected.id)}
                  disabled={assignMutation.isPending}
                >
                  {assignMutation.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    "Confirmar"
                  )}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1 h-7 text-xs"
                  onClick={() => setSelected(null)}
                  disabled={assignMutation.isPending}
                >
                  Cancelar
                </Button>
              </div>
            </div>
          ) : (
            /* Agent list */
            <ul className="py-1 max-h-56 overflow-y-auto">
              {agents.map((agent) => (
                <li key={agent.id}>
                  <button
                    className="w-full flex items-center gap-2.5 px-3 py-2 hover:bg-muted transition-colors text-left"
                    onClick={() => setSelected(agent)}
                  >
                    <AgentAvatar name={agent.name} role={agent.role} />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium truncate">{agent.name}</div>
                      <div className="text-[10px] text-muted-foreground">
                        {ROLE_LABEL[agent.role] ?? agent.role}
                      </div>
                    </div>
                    <span className="text-[10px] text-muted-foreground shrink-0 bg-muted rounded-full px-1.5 py-0.5">
                      {agent.active_leads} leads
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
