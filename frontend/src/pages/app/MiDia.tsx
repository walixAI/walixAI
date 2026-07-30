import { useRef } from "react";
import { ClipboardList, CheckCircle2 } from "lucide-react";
import { useMyTasksToday, useCloseTask, type TaskTodayItem } from "@/lib/queries/tasks";
import { formatMXN } from "@/lib/queries/pipeline";
import { WBadge } from "@/components/walix/Badge";
import { KpiCardsSkeleton, ListRowsSkeleton } from "@/components/walix/Skeletons";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

// ── Column definitions ────────────────────────────────────────────────────────

const COLUMNS: { id: string; label: string; kinds: string[] }[] = [
  { id: "cobrar",      label: "Cobrar hoy",      kinds: ["cobro"] },
  { id: "cotizar",     label: "Cotizar",          kinds: ["cotizacion"] },
  { id: "servicios",   label: "Servicios de hoy", kinds: ["servicio"] },
  { id: "seguimiento", label: "Seguimiento",       kinds: ["seguimiento"] },
  { id: "otras",       label: "Otras tareas",      kinds: ["queja", "refaccion", "facturacion", "devolucion", "otro"] },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function SummaryChip({
  label,
  value,
  danger,
  onClick,
}: {
  label: string;
  value: string;
  danger?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "flex flex-col items-start rounded-xl border px-4 py-3 text-left transition-colors",
        onClick ? "cursor-pointer hover:bg-accent" : "cursor-default",
        danger
          ? "border-danger/20 bg-danger/5"
          : "border-border bg-card",
      ].join(" ")}
    >
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className={[
        "mt-0.5 text-lg font-semibold",
        danger ? "text-danger" : "text-foreground",
      ].join(" ")}>
        {value}
      </span>
    </button>
  );
}

function TaskCard({
  item,
  onComplete,
  completing,
}: {
  item: TaskTodayItem;
  onComplete: () => void;
  completing: boolean;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-card space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">
            {item.title ?? item.taskKind ?? "Tarea"}
          </p>
          {item.leadName && (
            <p className="truncate text-xs text-muted-foreground">{item.leadName}</p>
          )}
        </div>
        {item.overdue && (
          <WBadge variant="danger" className="shrink-0">Vencida</WBadge>
        )}
      </div>

      {(item.dealTitle || item.dealAmount !== null) && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {item.dealTitle && <span className="truncate">{item.dealTitle}</span>}
          {item.dealAmount !== null && (
            <span className="shrink-0 font-medium text-foreground">
              {formatMXN(item.dealAmount)}
            </span>
          )}
        </div>
      )}

      <Button
        size="sm"
        variant="outline"
        className="w-full mt-1"
        onClick={onComplete}
        disabled={completing}
      >
        <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />
        Completar
      </Button>
    </div>
  );
}

function ColumnGroup({
  label,
  items,
  colRef,
  onComplete,
  completingIds,
}: {
  label: string;
  items: TaskTodayItem[];
  colRef?: React.RefObject<HTMLDivElement>;
  onComplete: (item: TaskTodayItem) => void;
  completingIds: Set<string>;
}) {
  return (
    <div ref={colRef} className="space-y-3 scroll-mt-4">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-foreground">{label}</h2>
        <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-muted px-1.5 text-[11px] font-medium text-muted-foreground">
          {items.length}
        </span>
      </div>

      {items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
          Sin tareas pendientes
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {items.map((item) => (
            <TaskCard
              key={item.id}
              item={item}
              onComplete={() => onComplete(item)}
              completing={completingIds.has(item.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MiDia() {
  const { data, isPending } = useMyTasksToday();
  const { mutate: closeTask, isPending: isClosing, variables: closingVars } = useCloseTask();

  const cobrarRef = useRef<HTMLDivElement>(null);
  const cotizarRef = useRef<HTMLDivElement>(null);

  const colScrollRefs: Record<string, React.RefObject<HTMLDivElement>> = {
    cobrar: cobrarRef,
    cotizar: cotizarRef,
  };

  function scrollToCol(ref: React.RefObject<HTMLDivElement>) {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (isPending) {
    return (
      <div className="p-4 md:p-6 space-y-6">
        <KpiCardsSkeleton count={3} />
        <ListRowsSkeleton />
      </div>
    );
  }

  const totals = data?.totals;
  const items = data?.items ?? [];

  const completingIds = new Set(
    isClosing && closingVars ? [closingVars.activityId] : []
  );

  function handleComplete(item: TaskTodayItem) {
    closeTask(
      { leadId: item.leadId, activityId: item.id, closedVia: "manual" },
      { onError: (e) => toast.error((e as Error).message ?? "Error al completar") },
    );
  }

  function getItems(kinds: string[]) {
    return items.filter((t) => t.taskKind !== null && kinds.includes(t.taskKind!));
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-primary/10 p-2">
          <ClipboardList className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-foreground">Mi Día</h1>
          <p className="text-sm text-muted-foreground">Tareas pendientes para hoy</p>
        </div>
      </div>

      {/* Summary chips */}
      <div className="flex flex-wrap gap-3">
        <SummaryChip
          label="Tareas hoy"
          value={String(totals?.total ?? 0)}
          danger={(totals?.overdue ?? 0) > 0}
        />
        <SummaryChip
          label="Por cobrar"
          value={formatMXN(totals?.collectAmount ?? 0)}
          onClick={() => scrollToCol(cobrarRef)}
        />
        <SummaryChip
          label="Por cotizar"
          value={String(totals?.byKind?.cotizacion ?? 0)}
          onClick={() => scrollToCol(cotizarRef)}
        />
      </div>

      {/* Column groups */}
      <div className="space-y-8">
        {COLUMNS.map((col) => (
          <ColumnGroup
            key={col.id}
            label={col.label}
            items={getItems(col.kinds)}
            colRef={colScrollRefs[col.id]}
            onComplete={handleComplete}
            completingIds={completingIds}
          />
        ))}
      </div>
    </div>
  );
}
