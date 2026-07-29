import { useState } from "react";
import { X, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useOpportunityStore } from "../opportunityStore";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";

export function BulkActionBar() {
  const { selectedIds, stages, clearSelection, removeCard } = useOpportunityStore();
  const [moveStageId, setMoveStageId] = useState("");
  const [moving, setMoving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const count = selectedIds.size;
  if (count === 0) return null;

  const ids = Array.from(selectedIds);

  async function handleBulkMove() {
    if (!moveStageId) return;
    setMoving(true);
    try {
      await api.bulkMoveOpportunities(ids, moveStageId);
      // Refresh board
      const { branchId, fetchBoard } = useOpportunityStore.getState();
      await fetchBoard(branchId ?? undefined);
      clearSelection();
      const stageName = stages.find((s) => s.id === moveStageId)?.name ?? "la etapa";
      toast.success(`${count} oportunidad${count !== 1 ? "es" : ""} movida${count !== 1 ? "s" : ""} a "${stageName}"`);
    } catch (e) {
      toast.error("No se pudo mover la selección", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setMoving(false);
    }
  }

  async function handleBulkDelete() {
    setDeleting(true);
    try {
      await api.bulkDeleteOpportunities(ids);
      ids.forEach((id) => removeCard(id));
      clearSelection();
      toast.success(`${count} oportunidad${count !== 1 ? "es" : ""} eliminada${count !== 1 ? "s" : ""}`);
    } catch (e) {
      toast.error("No se pudieron eliminar las oportunidades", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div
      className={cn(
        "fixed bottom-[72px] left-1/2 -translate-x-1/2 z-20",
        "flex items-center gap-3 px-4 py-2.5 rounded-2xl",
        "bg-card border border-border shadow-lg",
      )}
      role="toolbar"
      aria-label="Acciones en masa"
    >
      <span className="text-sm font-semibold text-foreground shrink-0">
        {count} seleccionada{count !== 1 ? "s" : ""}
      </span>

      <div className="flex items-center gap-2">
        <select
          value={moveStageId}
          onChange={(e) => setMoveStageId(e.target.value)}
          className="h-8 rounded-lg border border-input bg-background px-2 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="Seleccionar etapa destino"
        >
          <option value="">Mover a etapa…</option>
          {stages
            .filter((s) => !s.is_lost)
            .map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
        </select>
        <Button
          size="sm"
          className="h-8 text-xs"
          onClick={handleBulkMove}
          disabled={!moveStageId || moving}
          aria-label="Mover seleccionadas a la etapa elegida"
        >
          {moving ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : "Mover"}
        </Button>
      </div>

      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            size="sm"
            variant="destructive"
            className="h-8 text-xs"
            disabled={deleting}
            aria-label={`Eliminar ${count} oportunidad${count !== 1 ? "es" : ""} seleccionada${count !== 1 ? "s" : ""}`}
          >
            {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : "Eliminar"}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar {count} oportunidad{count !== 1 ? "es" : ""}?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción no se puede deshacer. Las oportunidades serán eliminadas permanentemente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleBulkDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <button
        type="button"
        onClick={clearSelection}
        className="h-7 w-7 rounded-full flex items-center justify-center hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-primary"
        aria-label="Limpiar selección"
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
