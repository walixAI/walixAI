import { useState } from "react";
import { Trash2, UserCheck, Tag, Download, MessageSquare, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

interface BulkActionsInlineProps {
  selectedIds: Set<string>;
  onClear: () => void;
  onDelete: (ids: string[]) => Promise<void>;
  onReassign?: (ids: string[]) => void;
  onChangeStatus?: (ids: string[]) => void;
  onTag?: (ids: string[]) => void;
  onExport?: (ids: string[]) => void;
}

export function BulkActionsInline({
  selectedIds,
  onClear,
  onDelete,
  onReassign,
  onChangeStatus,
  onTag,
  onExport,
}: BulkActionsInlineProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const ids = [...selectedIds];
  const n = ids.length;

  if (n === 0) return null;

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await onDelete(ids);
    } finally {
      setDeleting(false);
      setConfirmOpen(false);
    }
  };

  return (
    <>
      <div data-testid="bulk-actions-bar" className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 rounded-xl border border-border bg-popover px-4 py-2.5 shadow-xl shadow-black/10">
        <span className="text-sm font-medium text-foreground mr-1">
          {n} contacto{n !== 1 ? "s" : ""} seleccionado{n !== 1 ? "s" : ""}
        </span>

        <div className="w-px h-5 bg-border mx-0.5" />

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => onReassign?.(ids)}>
              <UserCheck className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Reasignar</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => onChangeStatus?.(ids)}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Cambiar estado</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => onTag?.(ids)}>
              <Tag className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Etiquetar</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => onExport?.(ids)}>
              <Download className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Exportar selección</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button data-testid="bulk-wa-btn" variant="ghost" size="sm" className="h-7 px-2 opacity-40 cursor-not-allowed" disabled>
              <MessageSquare className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>WhatsApp masivo — Próximamente en Sprint 8</TooltipContent>
        </Tooltip>

        <div className="w-px h-5 bg-border mx-0.5" />

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              data-testid="bulk-delete-btn"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-destructive hover:text-destructive hover:bg-destructive/10"
              onClick={() => setConfirmOpen(true)}
              disabled={deleting}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Eliminar selección</TooltipContent>
        </Tooltip>

        <Button variant="ghost" size="sm" className="h-7 px-2 text-muted-foreground" onClick={onClear}>
          ✕
        </Button>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title={`Eliminar ${n} contacto${n !== 1 ? "s" : ""}`}
        description={
          n > 10
            ? `Esta acción eliminará permanentemente ${n} contactos. Escribe ELIMINAR para confirmar.`
            : `Esta acción eliminará permanentemente ${n} contacto${n !== 1 ? "s" : ""}. ¿Confirmas?`
        }
        confirmLabel={deleting ? "Eliminando…" : "Eliminar"}
        requireText={n > 10 ? "ELIMINAR" : undefined}
        destructive
        onConfirm={handleDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
