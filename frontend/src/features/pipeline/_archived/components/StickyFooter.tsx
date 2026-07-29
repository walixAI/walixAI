import { cn } from "@/lib/utils";
import { useOpportunityStore } from "../opportunityStore";

function formatMXN(n: number): string {
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n);
}

export function StickyFooter({ className }: { className?: string }) {
  const { stages, boardByStage } = useOpportunityStore();

  if (stages.length === 0) return null;

  const stageTotals = stages.map((stage) => {
    const cards = (boardByStage[stage.id] ?? []).filter((c) => c.status === "open");
    const total = cards.reduce((acc, c) => acc + parseFloat(c.amount ?? "0"), 0);
    return { stage, total };
  });

  const grandTotal = stageTotals.reduce((acc, s) => acc + s.total, 0);

  return (
    <div
      className={cn(
        "fixed bottom-0 left-0 right-0 z-10",
        "bg-card/95 backdrop-blur-sm border-t border-border",
        "flex items-center gap-1 px-4 py-2 overflow-x-auto",
        className,
      )}
      role="status"
      aria-label="Totales por etapa"
    >
      {stageTotals.map(({ stage, total }) => (
        <div
          key={stage.id}
          className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-muted/50 shrink-0"
        >
          <span
            className="h-2 w-2 rounded-full shrink-0"
            style={{ backgroundColor: stage.color ?? "hsl(var(--primary))" }}
            aria-hidden="true"
          />
          <span className="text-[11px] text-muted-foreground font-medium truncate max-w-[80px]">
            {stage.name}
          </span>
          <span className="text-[11px] font-semibold tabular-nums">
            {total > 0 ? formatMXN(total) : "—"}
          </span>
        </div>
      ))}

      <div className="ml-auto shrink-0 flex items-center gap-2 pl-3 border-l border-border">
        <span className="text-xs text-muted-foreground font-medium">
          Total pipeline
        </span>
        <span className="text-sm font-bold tabular-nums">
          {formatMXN(grandTotal)}
        </span>
      </div>
    </div>
  );
}
