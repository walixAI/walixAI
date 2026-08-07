import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Lock, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { apiRequest } from "@/lib/queries/_client";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";

interface CatalogItem {
  key: string;
  name: string;
  description: string | null;
  is_mandatory: boolean;
}

interface LayoutItem {
  key: string;
  position: number;
  hidden: boolean;
  is_mandatory: boolean;
}

interface LocalItem {
  key: string;
  name: string;
  description: string | null;
  is_mandatory: boolean;
  hidden: boolean;
}

export interface CustomizeSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scope: "user" | "role" | "tenant_default";
  role?: string;
  panelKey: string;
}

function SortableRow({ item, onToggle }: { item: LocalItem; onToggle: (key: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.key,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-3"
    >
      <button
        {...attributes}
        {...listeners}
        className="text-muted-foreground cursor-grab active:cursor-grabbing shrink-0 touch-none"
        tabIndex={-1}
        aria-label="Arrastrar"
      >
        <GripVertical className="h-4 w-4" />
      </button>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{item.name}</p>
        {item.description && (
          <p className="text-xs text-muted-foreground truncate">{item.description}</p>
        )}
      </div>

      {item.is_mandatory ? (
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="shrink-0 flex items-center gap-1.5 text-muted-foreground">
                <Lock className="h-3.5 w-3.5" />
                <Switch checked={true} disabled aria-label="Siempre visible" />
              </span>
            </TooltipTrigger>
            <TooltipContent side="left">
              <p>Este widget no se puede ocultar</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : (
        <Switch
          checked={!item.hidden}
          onCheckedChange={() => onToggle(item.key)}
          className="shrink-0"
          aria-label={item.hidden ? "Mostrar widget" : "Ocultar widget"}
        />
      )}
    </div>
  );
}

export function CustomizeSheet({ open, onOpenChange, scope, role, panelKey }: CustomizeSheetProps) {
  const qc = useQueryClient();
  const [items, setItems] = useState<LocalItem[]>([]);

  const { data: catalog } = useQuery({
    queryKey: ["dashboard-catalog", panelKey],
    queryFn: () => apiRequest<CatalogItem[]>(`/api/dashboard/widgets-catalog?panel=${encodeURIComponent(panelKey)}`),
    staleTime: 300_000,
  });

  const { data: layout } = useQuery({
    queryKey: ["dashboard-layout", panelKey],
    queryFn: () => apiRequest<LayoutItem[]>(`/api/dashboard/layout?panel=${encodeURIComponent(panelKey)}`),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!open || !catalog || !layout) return;
    const layoutMap = new Map(layout.map((l) => [l.key, l]));
    const merged: LocalItem[] = catalog
      .map((c) => {
        const l = layoutMap.get(c.key);
        return {
          key: c.key,
          name: c.name,
          description: c.description,
          is_mandatory: c.is_mandatory,
          hidden: l ? l.hidden : false,
        };
      })
      .sort((a, b) => {
        const pa = layoutMap.get(a.key)?.position ?? 9999;
        const pb = layoutMap.get(b.key)?.position ?? 9999;
        return pa - pb;
      });
    setItems(merged);
  }, [open, catalog, layout]);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setItems((prev) => {
      const oldIdx = prev.findIndex((i) => i.key === active.id);
      const newIdx = prev.findIndex((i) => i.key === over.id);
      return arrayMove(prev, oldIdx, newIdx);
    });
  }

  function toggleHidden(key: string) {
    setItems((prev) => prev.map((i) => (i.key === key ? { ...i, hidden: !i.hidden } : i)));
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      let url = `/api/dashboard/layout?scope=${scope}&panel=${encodeURIComponent(panelKey)}`;
      if (scope === "role" && role) url += `&role=${role}`;
      return apiRequest<void>(url, {
        method: "PUT",
        body: JSON.stringify({
          items: items.map((item, idx) => ({
            key: item.key,
            position: (idx + 1) * 10,
            hidden: item.is_mandatory ? false : item.hidden,
          })),
        }),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard-layout", panelKey] });
      toast.success("Layout guardado");
      onOpenChange(false);
    },
    onError: (e: Error) =>
      toast.error("Error al guardar", { description: e.message }),
  });

  const isLoading = !catalog || !layout;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md flex flex-col gap-0 p-0">
        <SheetHeader className="px-5 py-4 border-b border-border">
          <SheetTitle>Personalizar dashboard</SheetTitle>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
            </div>
          ) : (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={items.map((i) => i.key)}
                strategy={verticalListSortingStrategy}
              >
                <div className="space-y-2">
                  {items.map((item) => (
                    <SortableRow key={item.key} item={item} onToggle={toggleHidden} />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          )}
        </div>

        <SheetFooter className="px-5 py-4 border-t border-border flex-row gap-2">
          <Button
            className="flex-1"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || isLoading}
          >
            {saveMutation.isPending && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
            Guardar
          </Button>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
