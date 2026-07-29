import { useState, useRef, useCallback } from "react";
import {
  Search,
  X,
  LayoutGrid,
  List,
  SlidersHorizontal,
  Sparkles,
  Plus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useOpportunityStore } from "../opportunityStore";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface PipelineHeaderProps {
  onNewOpportunity?: () => void;
  onInsightsAI?: () => void;
}

export function PipelineHeader({ onNewOpportunity, onInsightsAI }: PipelineHeaderProps) {
  const { view, setView, filters, setFilter, resetFilters } = useOpportunityStore();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const handleSearchClear = useCallback(() => {
    setFilter("search", "");
    searchRef.current?.focus();
  }, [setFilter]);

  const hasActiveFilters =
    filters.assignedTo ||
    filters.minAmount != null ||
    filters.maxAmount != null ||
    filters.closeDateBefore ||
    filters.source;

  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* Title */}
      <h1 className="text-xl font-bold tracking-tight shrink-0">
        Pipeline Principal
      </h1>

      {/* Search */}
      <div className="relative flex-1 min-w-[200px] max-w-[320px]">
        <Search
          className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none"
          aria-hidden="true"
        />
        <input
          ref={searchRef}
          type="search"
          placeholder="Buscar oportunidad…"
          value={filters.search}
          onChange={(e) => setFilter("search", e.target.value)}
          className={cn(
            "w-full h-8 pl-8 pr-7 rounded-lg border border-border bg-background text-sm",
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary",
          )}
          aria-label="Buscar oportunidades"
        />
        {filters.search && (
          <button
            type="button"
            onClick={handleSearchClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            aria-label="Limpiar búsqueda"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* View toggle */}
      <div
        role="group"
        aria-label="Cambiar vista"
        className="flex items-center rounded-lg border border-border overflow-hidden"
      >
        <button
          type="button"
          onClick={() => setView("kanban")}
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium transition-colors",
            view === "kanban"
              ? "bg-primary text-primary-foreground"
              : "hover:bg-muted text-muted-foreground",
          )}
          aria-pressed={view === "kanban"}
          aria-label="Vista Kanban"
        >
          <LayoutGrid className="h-3.5 w-3.5" aria-hidden="true" />
          Kanban
        </button>
        <button
          type="button"
          onClick={() => setView("list")}
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium transition-colors",
            view === "list"
              ? "bg-primary text-primary-foreground"
              : "hover:bg-muted text-muted-foreground",
          )}
          aria-pressed={view === "list"}
          aria-label="Vista Lista"
        >
          <List className="h-3.5 w-3.5" aria-hidden="true" />
          Lista
        </button>
      </div>

      {/* Filters popover */}
      <Popover open={filtersOpen} onOpenChange={setFiltersOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className={cn(
              "gap-1.5 h-8 text-xs",
              hasActiveFilters && "border-primary text-primary",
            )}
            aria-label={hasActiveFilters ? "Filtros activos" : "Abrir filtros"}
          >
            <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
            Filtros
            {hasActiveFilters && (
              <span className="ml-0.5 h-4 w-4 rounded-full bg-primary text-primary-foreground text-[10px] font-bold flex items-center justify-center">
                •
              </span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-4 space-y-4" align="end">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">Filtros</p>
            {hasActiveFilters && (
              <button
                type="button"
                onClick={resetFilters}
                className="text-xs text-muted-foreground hover:text-foreground underline"
              >
                Limpiar
              </button>
            )}
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Monto mínimo (MXN)</Label>
            <Input
              type="number"
              min={0}
              placeholder="0"
              value={filters.minAmount ?? ""}
              onChange={(e) =>
                setFilter("minAmount", e.target.value ? Number(e.target.value) : null)
              }
              className="h-8 text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Monto máximo (MXN)</Label>
            <Input
              type="number"
              min={0}
              placeholder="Sin límite"
              value={filters.maxAmount ?? ""}
              onChange={(e) =>
                setFilter("maxAmount", e.target.value ? Number(e.target.value) : null)
              }
              className="h-8 text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Cierre antes de</Label>
            <Input
              type="date"
              value={filters.closeDateBefore ?? ""}
              onChange={(e) => setFilter("closeDateBefore", e.target.value || null)}
              className="h-8 text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Fuente</Label>
            <Input
              placeholder="ej. whatsapp, referido…"
              value={filters.source ?? ""}
              onChange={(e) => setFilter("source", e.target.value || null)}
              className="h-8 text-sm"
            />
          </div>

          <Button
            size="sm"
            className="w-full"
            onClick={() => setFiltersOpen(false)}
          >
            Aplicar filtros
          </Button>
        </PopoverContent>
      </Popover>

      {/* Insights IA */}
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5 h-8 text-xs"
        onClick={onInsightsAI}
        aria-label="Abrir panel de Insights IA"
      >
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        Insights IA
      </Button>

      {/* Nueva Oportunidad */}
      <Button
        size="sm"
        className="gap-1.5 h-8 text-xs"
        onClick={onNewOpportunity}
        aria-label="Crear nueva oportunidad"
      >
        <Plus className="h-3.5 w-3.5" aria-hidden="true" />
        Nueva Oportunidad
      </Button>
    </div>
  );
}
