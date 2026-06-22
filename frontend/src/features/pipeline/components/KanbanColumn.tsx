import { useMemo } from "react";
import { Plus } from "lucide-react";
import { useDroppable } from "@dnd-kit/core";
import { cn } from "@/lib/utils";
import type { OppBoardStage, OppCard } from "@/lib/api";
import { useOpportunityStore } from "@/stores/opportunityStore";
import { DraggableOppCard } from "./OpportunityCard";

function formatMXN(n: string | number | null | undefined): string {
  if (n === null || n === undefined) return "";
  const val = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(val) || val === 0) return "";
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

interface KanbanColumnProps {
  stage: OppBoardStage;
  cards: OppCard[];
  onAddNew?: () => void;
  onCardClick?: (oppId: string) => void;
}

export function KanbanColumn({ stage, cards, onAddNew, onCardClick }: KanbanColumnProps) {
  const { isOver, setNodeRef } = useDroppable({ id: stage.id });
  const { selectedIds, toggleSelect, filters } = useOpportunityStore();
  const hasSelection = selectedIds.size > 0;

  const filteredCards = useMemo(() => {
    let result = cards;
    if (filters.search) {
      const q = filters.search.toLowerCase();
      result = result.filter(
        (c) =>
          c.title.toLowerCase().includes(q) ||
          (c.lead_name ?? "").toLowerCase().includes(q) ||
          (c.assigned_to_name ?? "").toLowerCase().includes(q),
      );
    }
    if (filters.minAmount != null) {
      result = result.filter((c) => parseFloat(c.amount ?? "0") >= filters.minAmount!);
    }
    if (filters.maxAmount != null) {
      result = result.filter((c) => parseFloat(c.amount ?? "0") <= filters.maxAmount!);
    }
    if (filters.closeDateBefore) {
      result = result.filter(
        (c) => c.close_date && c.close_date <= filters.closeDateBefore!,
      );
    }
    if (filters.source) {
      result = result.filter((c) =>
        (c as unknown as { source?: string }).source
          ?.toLowerCase()
          .includes(filters.source!.toLowerCase()),
      );
    }
    return result;
  }, [cards, filters]);

  const openCount = filteredCards.filter((c) => c.status === "open").length;
  const isBottleneck = openCount > 10;

  const totalAmount = filteredCards
    .filter((c) => c.status === "open")
    .reduce((acc, c) => acc + parseFloat(c.amount ?? "0"), 0);

  return (
    <div
      className={cn(
        "w-[85vw] max-w-[320px] sm:w-[272px] shrink-0 snap-center snap-always flex flex-col rounded-xl border border-border bg-card/50",
        isBottleneck && "border-t-2 border-t-warning",
      )}
      role="region"
      aria-label={`Etapa: ${stage.name}`}
    >
      {/* Colored top strip */}
      <div
        className="h-1 rounded-t-xl shrink-0"
        style={{ backgroundColor: stage.color ?? "hsl(var(--primary))" }}
        aria-hidden="true"
      />

      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
        <span
          className="h-2 w-2 rounded-full shrink-0"
          style={{ backgroundColor: stage.color ?? "hsl(var(--primary))" }}
          aria-hidden="true"
        />
        <span className="text-sm font-semibold truncate flex-1">{stage.name}</span>

        {/* Bottleneck chip */}
        {isBottleneck && (
          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-warning/10 text-warning border border-warning/20 shrink-0">
            Cuello
          </span>
        )}

        <span
          className={cn(
            "text-xs font-medium tabular-nums px-1.5 py-0.5 rounded-full shrink-0",
            filteredCards.length > 0
              ? "bg-primary/10 text-primary"
              : "bg-muted text-muted-foreground",
          )}
          aria-label={`${filteredCards.length} oportunidades`}
        >
          {filteredCards.length}
        </span>

        {totalAmount > 0 && (
          <span className="text-[10px] text-muted-foreground tabular-nums shrink-0 hidden sm:block">
            {formatMXN(String(totalAmount))}
          </span>
        )}

        <button
          type="button"
          onClick={onAddNew}
          className="h-5 w-5 rounded flex items-center justify-center hover:bg-muted text-muted-foreground hover:text-foreground transition-colors focus-visible:ring-2 focus-visible:ring-primary shrink-0"
          aria-label={`Agregar oportunidad en ${stage.name}`}
        >
          <Plus className="h-3 w-3" aria-hidden="true" />
        </button>
      </div>

      {/* Drop zone */}
      <div
        ref={setNodeRef}
        className={cn(
          "flex-1 overflow-y-auto p-2 space-y-2 min-h-[120px] rounded-b-xl transition-colors duration-150",
          isOver && !stage.is_lost && "bg-primary/5",
          isOver && stage.is_lost && "bg-danger/5",
        )}
      >
        {filteredCards.length === 0 ? (
          <p className="text-[11px] text-muted-foreground text-center py-8 select-none">
            Sin oportunidades aún — arrastra una aquí o crea una nueva
          </p>
        ) : (
          filteredCards.map((card) => (
            <DraggableOppCard
              key={card.id}
              opp={card}
              isSelected={selectedIds.has(card.id)}
              hasSelection={hasSelection}
              onSelect={toggleSelect}
              onClick={() => onCardClick?.(card.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
