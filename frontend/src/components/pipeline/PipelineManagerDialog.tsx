import { useState } from "react";
import { Check, Pencil, Plus, Settings, Trash2, X } from "lucide-react";
import { z } from "zod";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { WBadge } from "@/components/walix/Badge";
import { useTenantLabels } from "@/hooks/useTenantLabels";
import {
  usePipelines,
  useCreatePipeline,
  useRenamePipeline,
  useDeletePipeline,
} from "@/lib/queries/pipeline";

const nameSchema = z
  .string()
  .trim()
  .min(1, "El nombre es obligatorio")
  .max(60, "Máximo 60 caracteres");

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect?: (id: string) => void;
}

export function PipelineManagerDialog({ open, onClose, onSelect }: Props) {
  const { deals } = useTenantLabels();
  const { data: pipelines = [] } = usePipelines();

  const createMut = useCreatePipeline();
  const renameMut = useRenamePipeline();
  const deleteMut = useDeletePipeline();

  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const branchId = pipelines[0]?.branchId ?? null;

  function startEdit(id: string, currentName: string) {
    setEditingId(id);
    setEditingName(currentName);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditingName("");
  }

  async function commitEdit(id: string) {
    const parsed = nameSchema.safeParse(editingName);
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? "Nombre inválido");
      return;
    }
    try {
      await renameMut.mutateAsync({ id, name: parsed.data });
      toast.success("Pipeline renombrado");
      cancelEdit();
    } catch (e: any) {
      toast.error(e?.message ?? "No se pudo renombrar");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent, id: string) {
    if (e.key === "Enter") commitEdit(id);
    if (e.key === "Escape") cancelEdit();
  }

  async function handleCreate() {
    const parsed = nameSchema.safeParse(newName);
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? "Nombre inválido");
      return;
    }
    if (!branchId) {
      toast.error("No se encontró una sucursal activa");
      return;
    }
    try {
      const created = await createMut.mutateAsync({ name: parsed.data, branch_id: branchId });
      toast.success("Pipeline creado");
      setNewName("");
      onSelect?.(created.id);
    } catch (e: any) {
      toast.error(e?.message ?? "No se pudo crear el pipeline");
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteMut.mutateAsync(id);
      toast.success("Pipeline eliminado");
      setConfirmDeleteId(null);
    } catch (e: any) {
      // e.message contiene el detail exacto del 409 que devuelve el backend
      toast.error(e?.message ?? "No se pudo eliminar el pipeline");
      setConfirmDeleteId(null);
    }
  }

  const confirmTarget = pipelines.find((p) => p.id === confirmDeleteId);

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Settings className="h-4 w-4 text-muted-foreground" />
              Gestionar pipelines
            </DialogTitle>
          </DialogHeader>

          <ScrollArea className="max-h-[300px] pr-1">
            <div className="space-y-1 py-1">
              {pipelines.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-6">
                  No hay pipelines disponibles
                </p>
              )}
              {pipelines.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50"
                >
                  {editingId === p.id ? (
                    <>
                      <Input
                        className="h-7 text-sm flex-1"
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, p.id)}
                        autoFocus
                        maxLength={60}
                      />
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 text-success hover:text-success hover:bg-success/10"
                        onClick={() => commitEdit(p.id)}
                        disabled={renameMut.isPending}
                      >
                        <Check className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={cancelEdit}
                      >
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    </>
                  ) : (
                    <>
                      <span className="flex-1 text-sm truncate">{p.name}</span>
                      {p.isDefault && (
                        <WBadge variant="brand">Default</WBadge>
                      )}
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 text-muted-foreground hover:text-foreground"
                        onClick={() => startEdit(p.id, p.name)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 text-muted-foreground hover:text-danger hover:bg-danger/10"
                        onClick={() => setConfirmDeleteId(p.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>

          <div className="border-t border-border pt-3">
            {branchId ? (
              <div className="flex gap-2">
                <Input
                  className="h-8 text-sm"
                  placeholder="Nombre del nuevo pipeline…"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  maxLength={60}
                />
                <Button
                  size="sm"
                  className="h-8 shrink-0"
                  onClick={handleCreate}
                  disabled={createMut.isPending || !newName.trim()}
                >
                  <Plus className="h-3.5 w-3.5" />
                  {createMut.isPending ? "Creando…" : "Crear"}
                </Button>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-1">
                No hay una sucursal activa para crear pipelines.
              </p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={confirmDeleteId !== null}
        onOpenChange={(o) => !o && setConfirmDeleteId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              ¿Eliminar &ldquo;{confirmTarget?.name}&rdquo;?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Se eliminará el pipeline. Si tiene {deals.toLowerCase()} activos
              o es el único de la sucursal, la operación será rechazada.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              className="bg-danger hover:bg-danger/90 text-danger-foreground"
              onClick={() => confirmDeleteId && handleDelete(confirmDeleteId)}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? "Eliminando…" : "Eliminar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
