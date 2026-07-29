import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { apiRequest } from "@/lib/queries/_client";
import { type PipelineStage } from "@/lib/queries/pipeline";
import { useTenantLabels } from "@/hooks/useTenantLabels";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Props {
  selectedIds: string[];
  stages: PipelineStage[];
  onClear: () => void;
}

export function BulkActionsBar({ selectedIds, stages, onClear }: Props) {
  const qc = useQueryClient();
  const { deal, deals } = useTenantLabels();
  const [moving, setMoving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (selectedIds.length === 0) return null;

  const label = selectedIds.length === 1 ? deal.toLowerCase() : deals.toLowerCase();

  async function handleMoveToStage(stageId: string) {
    const stage = stages.find((s) => s.id === stageId);
    if (!stage) return;
    setMoving(true);
    try {
      await Promise.all(
        selectedIds.map((id) =>
          apiRequest(`/api/deals/${id}`, {
            method: "PATCH",
            body: JSON.stringify({
              pipeline_stage_id: stage.id,
              is_won: stage.isWon,
              is_lost: stage.isLost,
            }),
          }),
        ),
      );
      await qc.invalidateQueries({ queryKey: ["pipeline-deals"] });
      toast.success(`${selectedIds.length} ${label} movido${selectedIds.length !== 1 ? "s" : ""} a ${stage.name}`);
      onClear();
    } catch (e: unknown) {
      toast.error("Error al mover", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setMoving(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await Promise.all(
        selectedIds.map((id) =>
          apiRequest(`/api/deals/${id}`, { method: "DELETE" }),
        ),
      );
      await qc.invalidateQueries({ queryKey: ["pipeline-deals"] });
      toast.success(`${selectedIds.length} ${label} eliminado${selectedIds.length !== 1 ? "s" : ""}`);
      onClear();
    } catch (e: unknown) {
      toast.error("Error al eliminar", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setDeleting(false);
      setConfirmOpen(false);
    }
  }

  const busy = moving || deleting;

  return (
    <>
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 rounded-full border border-border bg-card shadow-lg px-4 py-2.5">
        <span className="text-sm font-medium text-foreground whitespace-nowrap">
          {selectedIds.length} {label} seleccionado{selectedIds.length !== 1 ? "s" : ""}
        </span>

        <div className="w-px h-4 bg-border mx-1" />

        <Select onValueChange={handleMoveToStage} disabled={busy}>
          <SelectTrigger className="h-7 text-xs rounded-full border-border bg-muted px-3 w-36">
            <SelectValue placeholder="Mover a etapa…" />
          </SelectTrigger>
          <SelectContent>
            {stages.filter((s) => !s.isWon && !s.isLost).map((s) => (
              <SelectItem key={s.id} value={s.id}>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
                  {s.name}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {moving && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}

        <button
          onClick={() => setConfirmOpen(true)}
          disabled={busy}
          className="flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Eliminar
        </button>

        <div className="w-px h-4 bg-border mx-1" />

        <button
          onClick={onClear}
          disabled={busy}
          className="rounded-full p-1 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50"
          aria-label="Deseleccionar todo"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              ¿Eliminar {selectedIds.length} {label}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción es permanente y no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
