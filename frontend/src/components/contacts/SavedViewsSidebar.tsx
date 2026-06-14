import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bookmark,
  BookmarkCheck,
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
  Pencil,
  Plus,
  Star,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  deleteSavedView,
  getSavedViews,
  setDefaultView,
  type SavedViewRow,
} from "@/lib/queries/saved_views";

interface SavedViewsSidebarProps {
  activeViewId: string | null;
  onApplyView: (view: SavedViewRow) => void;
  onOpenCreate: () => void;
  onOpenRename: (view: SavedViewRow) => void;
}

export function SavedViewsSidebar({
  activeViewId,
  onApplyView,
  onOpenCreate,
  onOpenRename,
}: SavedViewsSidebarProps) {
  const qc = useQueryClient();
  const [collapsed, setCollapsed] = useState(false);

  const { data: views = [], isLoading } = useQuery({
    queryKey: ["saved-views"],
    queryFn: getSavedViews,
    staleTime: 60_000,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteSavedView,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["saved-views"] });
      toast.success("Vista eliminada", { duration: 3000, position: "bottom-right" });
    },
    onError: (e: Error) =>
      toast.error(e.message, { duration: 3000, position: "bottom-right" }),
  });

  const defaultMutation = useMutation({
    mutationFn: setDefaultView,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["saved-views"] });
      toast.success("Vista principal actualizada", {
        duration: 3000,
        position: "bottom-right",
      });
    },
    onError: (e: Error) =>
      toast.error(e.message, { duration: 3000, position: "bottom-right" }),
  });

  // ── Collapsed strip ───────────────────────────────────────────────────────

  if (collapsed) {
    return (
      <div data-testid="saved-views-sidebar" className="flex flex-col items-center w-10 shrink-0 border-r border-border bg-muted/20 py-3 gap-3">
        <Button
          data-testid="sidebar-expand-btn"
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => setCollapsed(false)}
          title="Expandir vistas"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
        <Bookmark className="h-4 w-4 text-muted-foreground mt-1" />
      </div>
    );
  }

  // ── Expanded panel ────────────────────────────────────────────────────────

  return (
    <div data-testid="saved-views-sidebar" className="flex flex-col w-[200px] shrink-0 border-r border-border bg-muted/20 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border">
        <span className="text-xs font-semibold">Mis vistas</span>
        <div className="flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={onOpenCreate}
            title="Nueva vista"
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
          <Button
            data-testid="sidebar-collapse-btn"
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={() => setCollapsed(true)}
            title="Colapsar"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
        {isLoading && (
          <div className="px-3 py-1 space-y-1.5">
            <Skeleton className="h-7 w-full rounded" />
            <Skeleton className="h-7 w-full rounded" />
            <Skeleton className="h-7 w-full rounded" />
          </div>
        )}

        {!isLoading && views.length === 0 && (
          <div className="flex flex-col items-center justify-center px-3 py-8 text-center gap-2">
            <Bookmark className="h-6 w-6 text-muted-foreground/50" />
            <p className="text-[11px] text-muted-foreground leading-snug">
              Guarda combinaciones de filtros para acceder rápido
            </p>
          </div>
        )}

        {!isLoading &&
          views.map((view) => {
            const isActive = view.id === activeViewId;
            return (
              <div
                key={view.id}
                role="button"
                tabIndex={0}
                data-testid="view-item"
                data-view-id={view.id}
                className={`group flex items-center gap-1.5 mx-1 my-0.5 rounded px-2 py-1.5 cursor-pointer text-[12px] transition-colors border-l-2
                  ${
                    isActive
                      ? "bg-background border-primary"
                      : "border-transparent hover:bg-background/60"
                  }`}
                onClick={() => onApplyView(view)}
                onKeyDown={(e) => e.key === "Enter" && onApplyView(view)}
              >
                {view.isDefault ? (
                  <BookmarkCheck className="h-3.5 w-3.5 shrink-0 text-primary" />
                ) : (
                  <Bookmark className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                )}

                <span
                  className="flex-1 truncate"
                  title={view.name}
                >
                  {view.name}
                </span>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      data-testid="view-menu-btn"
                      variant="ghost"
                      size="icon"
                      className="h-5 w-5 opacity-0 group-hover:opacity-100 shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreHorizontal className="h-3 w-3" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-44">
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenRename(view);
                      }}
                    >
                      <Pencil className="h-3.5 w-3.5 mr-2" />
                      Renombrar
                    </DropdownMenuItem>
                    {!view.isDefault && (
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation();
                          defaultMutation.mutate(view.id);
                        }}
                      >
                        <Star className="h-3.5 w-3.5 mr-2" />
                        Establecer como default
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem
                      className="text-destructive focus:text-destructive"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteMutation.mutate(view.id);
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5 mr-2" />
                      Eliminar
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            );
          })}
      </div>
    </div>
  );
}
