import { useState, useEffect } from "react";
import { Plus, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
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
import { usePanels, useDeletePanel, type PanelOut } from "@/lib/queries/panels";
import { CreatePanelDialog } from "./CreatePanelDialog";

interface Props {
  activePanel: string;
  onPanelChange: (key: string) => void;
}

export function PanelSwitcher({ activePanel, onPanelChange }: Props) {
  const { data: panels = [], isLoading } = usePanels();
  const deletePanel = useDeletePanel();

  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PanelOut | null>(null);

  // If the active panel key is no longer in the list (e.g. deleted, or lost access),
  // fall back to "principal".
  useEffect(() => {
    if (!isLoading && panels.length > 0 && !panels.some((p) => p.key === activePanel)) {
      onPanelChange("principal");
    }
  }, [panels, isLoading, activePanel, onPanelChange]);

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await deletePanel.mutateAsync(deleteTarget.id);
      toast.success(`Panel "${deleteTarget.name}" eliminado`);
      if (activePanel === deleteTarget.key) onPanelChange("principal");
    } catch (err: any) {
      toast.error("No se pudo eliminar el panel", { description: err?.message });
    } finally {
      setDeleteTarget(null);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 h-9 text-sm text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Cargando paneles…
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center gap-1 border-b border-border">
        {panels.map((panel) => {
          const isActive = panel.key === activePanel;
          const isCustom = !panel.is_system;

          return (
            <div key={panel.key} className="relative flex items-center group">
              <button
                onClick={() => onPanelChange(panel.key)}
                className={`px-3 py-2 text-sm font-medium transition-colors whitespace-nowrap border-b-2 -mb-px ${
                  isActive
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                }`}
              >
                {panel.name}
              </button>

              {isCustom && isActive && (
                <button
                  onClick={(e) => { e.stopPropagation(); setDeleteTarget(panel); }}
                  className="ml-0.5 mr-1 p-0.5 rounded text-muted-foreground hover:text-danger hover:bg-danger/10 transition-colors"
                  aria-label={`Eliminar panel ${panel.name}`}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
          );
        })}

        <button
          onClick={() => setCreateOpen(true)}
          className="ml-1 flex items-center gap-1 px-2 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Crear panel"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      <CreatePanelDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(panel) => onPanelChange(panel.key)}
      />

      <AlertDialog open={!!deleteTarget} onOpenChange={(v) => { if (!v) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar panel</AlertDialogTitle>
            <AlertDialogDescription>
              ¿Eliminar el panel <strong>"{deleteTarget?.name}"</strong>? Esta acción no se puede deshacer.
              El layout guardado en este panel también se perderá.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-danger hover:bg-danger/90 text-danger-foreground"
            >
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
