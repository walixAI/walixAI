import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  createSavedView,
  updateSavedView,
} from "@/lib/queries/saved_views";
import type { ContactFilters } from "@/lib/queries/contacts";
import type { ViewMode } from "./ContactsViewToggle";
import { useTenantLabels } from "@/hooks/useTenantLabels";

const SOURCE_LABELS: Record<string, string> = {
  manual: "Manual",
  whatsapp_inbound: "WhatsApp",
  web_form: "Web",
  referral: "Referido",
};

function buildFilterBadges(
  filters: ContactFilters,
  getStatusLabel: (key: string) => string,
) {
  const badges: { label: string; value: string }[] = [];
  if (filters.status?.length)
    badges.push({
      label: "Estatus",
      value: filters.status.map((s) => getStatusLabel(s)).join(", "),
    });
  if (filters.source?.length)
    badges.push({
      label: "Fuente",
      value: filters.source.map((s) => SOURCE_LABELS[s] ?? s).join(", "),
    });
  if (filters.tag?.length)
    badges.push({
      label: "Etiquetas",
      value: `${filters.tag.length} seleccionada${filters.tag.length !== 1 ? "s" : ""}`,
    });
  if (filters.assigned?.length)
    badges.push({
      label: "Vendedor",
      value: `${filters.assigned.length} seleccionado${filters.assigned.length !== 1 ? "s" : ""}`,
    });
  if (filters.dateFrom || filters.dateTo) {
    const parts: string[] = [];
    if (filters.dateFrom) parts.push(`desde ${filters.dateFrom}`);
    if (filters.dateTo) parts.push(`hasta ${filters.dateTo}`);
    badges.push({ label: "Fecha", value: parts.join(" ") });
  }
  if (filters.q) badges.push({ label: "Búsqueda", value: filters.q });
  return badges;
}

interface SavedViewDialogProps {
  mode: "create" | "rename";
  currentFilters: ContactFilters;
  currentViewMode: ViewMode;
  viewId?: string;
  viewName?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SavedViewDialog({
  mode,
  currentFilters,
  currentViewMode,
  viewId,
  viewName: initialName = "",
  open,
  onOpenChange,
}: SavedViewDialogProps) {
  const qc = useQueryClient();
  const { getStatusLabel } = useTenantLabels();
  const [name, setName] = useState(initialName);
  const [isDefault, setIsDefault] = useState(false);

  useEffect(() => {
    if (open) {
      setName(initialName);
      setIsDefault(false);
    }
  }, [open, initialName]);

  const mutation = useMutation({
    mutationFn: () => {
      if (mode === "create") {
        return createSavedView({
          name: name.trim(),
          filters: currentFilters,
          viewMode:
            currentViewMode === "kanban"
              ? "kanban"
              : currentViewMode === "cards"
              ? "cards"
              : "list",
          isDefault,
        });
      }
      return updateSavedView(viewId!, { name: name.trim() });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["saved-views"] });
      toast.success("Vista guardada", { duration: 3000, position: "bottom-right" });
      onOpenChange(false);
    },
    onError: (e: Error) =>
      toast.error(e.message, { duration: 3000, position: "bottom-right" }),
  });

  const filterBadges = mode === "create" ? buildFilterBadges(currentFilters, getStatusLabel) : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "Guardar vista" : "Renombrar vista"}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="view-name">Nombre</Label>
            <Input
              id="view-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value.slice(0, 80))}
              placeholder="Ej: Mis leads sin respuesta"
              maxLength={80}
              onKeyDown={(e) => {
                if (e.key === "Enter" && name.trim().length >= 1)
                  mutation.mutate();
              }}
            />
            <p className="text-xs text-muted-foreground text-right">
              {name.length}/80
            </p>
          </div>

          {mode === "create" && (
            <div className="flex items-center gap-2">
              <Checkbox
                id="is-default"
                checked={isDefault}
                onCheckedChange={(v) => setIsDefault(Boolean(v))}
              />
              <Label
                htmlFor="is-default"
                className="font-normal cursor-pointer"
              >
                Marcar como vista principal
              </Label>
            </div>
          )}

          {filterBadges.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs text-muted-foreground font-medium">
                Filtros incluidos
              </p>
              <div className="flex flex-wrap gap-1.5">
                {filterBadges.map(({ label, value }) => (
                  <Badge key={label} variant="secondary" className="text-xs">
                    <span className="font-semibold mr-1">{label}:</span>
                    {value}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={name.trim().length < 1 || mutation.isPending}
          >
            {mutation.isPending ? "Guardando…" : "Guardar vista"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
