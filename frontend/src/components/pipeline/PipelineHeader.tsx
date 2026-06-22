import { KanbanSquare, List, Plus, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { PipelineFilters, type PipelineFiltersValue } from "./PipelineFilters";
import { ForecastKpis } from "./ForecastKpis";

interface Props {
  title?: string;
  view: "kanban" | "list";
  onView: (v: "kanban" | "list") => void;
  filters: PipelineFiltersValue;
  onFilters: (v: PipelineFiltersValue) => void;
  search: string;
  onSearch: (v: string) => void;
  onNew: () => void;
  totalAmount: number;
  weightedAmount: number;
  closingThisMonth: number;
  closingDeltaPct: number | null;
  activeCount: number;
}

export function PipelineHeader({
  title = "Pipeline Principal",
  view, onView, filters, onFilters, search, onSearch, onNew,
  totalAmount, weightedAmount, closingThisMonth, closingDeltaPct, activeCount,
}: Props) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {/* FASE 2: dropdown selector de pipelines (multi-pipeline). MVP = título estático. */}
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => onSearch(e.target.value.slice(0, 100))}
              placeholder="Buscar oportunidades…"
              className="h-9 pl-7 pr-7 w-[200px]"
            />
            {search && (
              <button
                type="button"
                onClick={() => onSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                aria-label="Limpiar búsqueda"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <ToggleGroup type="single" value={view} onValueChange={(v) => v && onView(v as any)} className="border border-border rounded-md">
            <ToggleGroupItem value="kanban" size="sm" aria-label="Kanban">
              <KanbanSquare className="h-3.5 w-3.5" /> Kanban
            </ToggleGroupItem>
            <ToggleGroupItem value="list" size="sm" aria-label="Lista">
              <List className="h-3.5 w-3.5" /> Lista
            </ToggleGroupItem>
          </ToggleGroup>

          <PipelineFilters value={filters} onChange={onFilters} />

          {/* FASE 2: botón "Insights IA" (AiInsightsPanel) */}

          <Button size="sm" className="h-9 bg-primary hover:bg-primary/90" onClick={onNew}>
            <Plus className="h-3.5 w-3.5" /> Nueva Oportunidad
          </Button>
        </div>
      </div>

      <ForecastKpis
        total={totalAmount}
        weighted={weightedAmount}
        closingThisMonth={closingThisMonth}
        closingDeltaPct={closingDeltaPct}
        activeCount={activeCount}
      />
    </div>
  );
}
