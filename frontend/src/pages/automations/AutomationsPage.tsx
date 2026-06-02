import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, ChevronDown, ChevronRight, Play, Pencil } from "lucide-react";
import { toast } from "sonner";
import { api, AutomationOut } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const AGENT_TYPES = [
  { value: "all", label: "Todos" },
  { value: "follow_up", label: "Seguimiento" },
  { value: "analysis", label: "Análisis" },
  { value: "closure", label: "Cierre" },
  { value: "config", label: "Configuración" },
];

const STATUSES = [
  { value: "all", label: "Todos los estados" },
  { value: "suggested", label: "Pendiente" },
  { value: "confirmed", label: "Confirmado" },
  { value: "executed", label: "Ejecutado" },
  { value: "dismissed", label: "Descartado" },
  { value: "failed", label: "Fallido" },
  { value: "expired", label: "Expirado" },
];

const STATUS_CLASSES: Record<string, string> = {
  suggested: "bg-warning/15 text-warning",
  accepted: "bg-warning/15 text-warning",
  confirmed: "bg-primary/15 text-primary",
  executed: "bg-success/15 text-success",
  dismissed: "bg-muted text-muted-foreground",
  failed: "bg-danger/15 text-danger",
  expired: "bg-muted text-muted-foreground",
};

const STATUS_LABELS: Record<string, string> = {
  suggested: "Pendiente",
  accepted: "Aceptado",
  confirmed: "Confirmado",
  executed: "Ejecutado",
  dismissed: "Descartado",
  failed: "Fallido",
  expired: "Expirado",
};

const TYPE_EMOJI: Record<string, string> = {
  follow_up: "🔔",
  analysis: "🔍",
  closure: "🎯",
  cierre: "🎯",
  config: "⚙️",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", STATUS_CLASSES[status] ?? "bg-muted text-muted-foreground")}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

// ── Row ───────────────────────────────────────────────────────────────────────

function AutomationRow({
  automation,
  onEdit,
}: {
  automation: AutomationOut;
  onEdit: (a: AutomationOut) => void;
}) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const canReExecute = ["dismissed", "failed"].includes(automation.status);

  const reExecMutation = useMutation({
    mutationFn: () => api.reExecuteAutomation(automation.id),
    onSuccess: () => {
      toast.success("Re-ejecución iniciada");
      qc.invalidateQueries({ queryKey: ["automations"] });
    },
    onError: (e: Error) => toast.error("Error", { description: e.message }),
  });

  return (
    <>
      <tr
        className="border-b border-border hover:bg-muted/30 transition-colors cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            {expanded ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />}
            <span className="text-sm">{TYPE_EMOJI[automation.agent_type] ?? "⚙️"}</span>
            <span className="text-xs text-muted-foreground capitalize">{automation.agent_type.replace(/_/g, " ")}</span>
          </div>
        </td>
        <td className="px-4 py-3 max-w-[260px]">
          <p className="text-sm truncate">{automation.suggestion_text}</p>
        </td>
        <td className="px-4 py-3">
          <StatusBadge status={automation.status} />
        </td>
        <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
          {new Date(automation.created_at).toLocaleDateString("es-MX", { day: "2-digit", month: "short" })}
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => onEdit(automation)}
              className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              title="Editar mensaje"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            {canReExecute && (
              <button
                onClick={() => reExecMutation.mutate()}
                disabled={reExecMutation.isPending}
                className="p-1.5 rounded-lg hover:bg-primary/15 text-muted-foreground hover:text-primary transition-colors disabled:opacity-50"
                title="Re-ejecutar"
              >
                {reExecMutation.isPending
                  ? <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  : <Play className="h-3.5 w-3.5" />}
              </button>
            )}
          </div>
        </td>
      </tr>

      {expanded && (
        <tr className="border-b border-border bg-muted/20">
          <td colSpan={5} className="px-8 py-3 space-y-1.5">
            <p className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Disparador:</span>{" "}
              {automation.trigger_description}
            </p>
            {automation.error_detail && (
              <p className="text-xs text-danger">
                <span className="font-medium">Error:</span> {automation.error_detail}
              </p>
            )}
            {automation.execution_result && (
              <p className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Resultado:</span>{" "}
                {JSON.stringify(automation.execution_result)}
              </p>
            )}
            {automation.responded_at && (
              <p className="text-xs text-muted-foreground">
                Respondida: {new Date(automation.responded_at).toLocaleString("es-MX")}
              </p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ── Edit dialog ───────────────────────────────────────────────────────────────

function EditDialog({
  automation,
  onClose,
}: {
  automation: AutomationOut | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [msg, setMsg] = useState(automation?.suggestion_text ?? "");

  const mutation = useMutation({
    mutationFn: (custom_message: string) =>
      api.updateAutomation(automation!.id, { custom_message }),
    onSuccess: () => {
      toast.success("Mensaje actualizado");
      qc.invalidateQueries({ queryKey: ["automations"] });
      onClose();
    },
    onError: (e: Error) => toast.error("Error", { description: e.message }),
  });

  if (!automation) return null;

  return (
    <Dialog open={Boolean(automation)} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base">Editar mensaje personalizado</DialogTitle>
        </DialogHeader>
        <textarea
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          rows={4}
          className="w-full rounded-lg border border-border bg-background px-3 py-2
                     text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/50"
        />
        <DialogFooter className="gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            size="sm"
            onClick={() => mutation.mutate(msg)}
            disabled={mutation.isPending || !msg.trim()}
          >
            {mutation.isPending ? <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AutomationsPage() {
  const [agentType, setAgentType] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [editTarget, setEditTarget] = useState<AutomationOut | null>(null);
  const LIMIT = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["automations", agentType, statusFilter, page],
    queryFn: () =>
      api.getAutomations({
        page,
        limit: LIMIT,
        agent_type: agentType === "all" ? undefined : agentType,
        status: statusFilter === "all" ? undefined : statusFilter,
      }),
    staleTime: 30_000,
  });

  const totalPages = data ? Math.ceil(data.total / LIMIT) : 1;

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight">Automatizaciones</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Repositorio de sugerencias y acciones del agente
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={agentType} onValueChange={(v) => { setAgentType(v); setPage(1); }}>
          <TabsList>
            {AGENT_TYPES.map((t) => (
              <TabsTrigger key={t.value} value={t.value} className="text-xs">
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1); }}>
          <SelectTrigger className="w-44 h-9 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUSES.map((s) => (
              <SelectItem key={s.value} value={s.value} className="text-xs">
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border bg-card shadow-card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground w-36">Tipo</th>
              <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Sugerencia</th>
              <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground w-28">Estado</th>
              <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground w-24">Creada</th>
              <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground w-20">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-border">
                  <td className="px-4 py-3"><Skeleton className="h-4 w-20" /></td>
                  <td className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                  <td className="px-4 py-3"><Skeleton className="h-5 w-20 rounded-full" /></td>
                  <td className="px-4 py-3"><Skeleton className="h-4 w-16" /></td>
                  <td className="px-4 py-3"><Skeleton className="h-7 w-16" /></td>
                </tr>
              ))
            ) : (data?.items ?? []).length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-sm text-muted-foreground">
                  Sin automatizaciones para los filtros seleccionados
                </td>
              </tr>
            ) : (
              data!.items.map((a) => (
                <AutomationRow key={a.id} automation={a} onEdit={setEditTarget} />
              ))
            )}
          </tbody>
        </table>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border">
            <p className="text-xs text-muted-foreground">
              {data?.total ?? 0} automatizaciones
            </p>
            <div className="flex gap-1.5">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="h-7 text-xs px-2"
              >
                Anterior
              </Button>
              <span className="text-xs text-muted-foreground flex items-center px-1">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="h-7 text-xs px-2"
              >
                Siguiente
              </Button>
            </div>
          </div>
        )}
      </div>

      <EditDialog automation={editTarget} onClose={() => setEditTarget(null)} />
    </div>
  );
}
