import { useState, useMemo } from "react";
import { ArrowUp, ArrowDown, ArrowUpDown, Download } from "lucide-react";
import { cn } from "@/lib/utils";
import { useOpportunityStore } from "../opportunityStore";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";

type SortCol =
  | "title"
  | "lead_name"
  | "amount"
  | "stage"
  | "probability"
  | "assigned_to_name"
  | "days_in_stage"
  | "close_date";
type SortDir = "asc" | "desc";

function formatMXN(n: string | number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const val = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(val)) return "—";
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

function avatarColor(id: string | null | undefined): string {
  const COLORS = ["#6B7FFF","#6ECE58","#FFB84D","#FF4242","#4FA8FF","#2DD4BF","#A855F7","#EC4899"];
  if (!id) return COLORS[0];
  let h = 0;
  for (const c of id) h = ((h * 31) + c.charCodeAt(0)) & 0xffffffff;
  return COLORS[Math.abs(h) % COLORS.length];
}

function initials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

function SortIcon({ col, active, dir }: { col: string; active: string; dir: SortDir }) {
  if (col !== active) return <ArrowUpDown className="h-3 w-3 text-muted-foreground/50" aria-hidden="true" />;
  return dir === "asc"
    ? <ArrowUp className="h-3 w-3 text-primary" aria-hidden="true" />
    : <ArrowDown className="h-3 w-3 text-primary" aria-hidden="true" />;
}

export function OpportunityTable() {
  const { stages, boardByStage, filters, loading, branchId, openDrawer } = useOpportunityStore();
  const [sortCol, setSortCol] = useState<SortCol>("title");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [exporting, setExporting] = useState(false);

  function handleSort(col: SortCol) {
    if (col === sortCol) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortCol(col); setSortDir("asc"); }
  }

  // Build stage lookup maps
  const stageOrderMap = useMemo(() => new Map(stages.map((s, i) => [s.id, i])), [stages]);
  const stageNameMap = useMemo(() => new Map(stages.map((s) => [s.id, s.name])), [stages]);
  const stageColorMap = useMemo(() => new Map(stages.map((s) => [s.id, s.color])), [stages]);

  const rows = useMemo(() => {
    // Flatten
    const all: Array<{ card: typeof boardByStage[string][number]; stageId: string }> = [];
    for (const [stageId, cards] of Object.entries(boardByStage)) {
      for (const card of cards) all.push({ card, stageId });
    }

    // Filter
    let filtered = all;
    if (filters.search) {
      const q = filters.search.toLowerCase();
      filtered = filtered.filter(
        ({ card }) =>
          card.title.toLowerCase().includes(q) ||
          (card.lead_name ?? "").toLowerCase().includes(q) ||
          (card.assigned_to_name ?? "").toLowerCase().includes(q),
      );
    }
    if (filters.minAmount != null)
      filtered = filtered.filter(({ card }) => parseFloat(card.amount ?? "0") >= filters.minAmount!);
    if (filters.maxAmount != null)
      filtered = filtered.filter(({ card }) => parseFloat(card.amount ?? "0") <= filters.maxAmount!);
    if (filters.closeDateBefore)
      filtered = filtered.filter(({ card }) => card.close_date && card.close_date <= filters.closeDateBefore!);

    // Sort
    filtered.sort((a, b) => {
      const ca = a.card, cb = b.card;
      let va: number | string, vb: number | string;
      switch (sortCol) {
        case "title": va = ca.title; vb = cb.title; break;
        case "lead_name": va = ca.lead_name ?? ""; vb = cb.lead_name ?? ""; break;
        case "amount": va = parseFloat(ca.amount ?? "0"); vb = parseFloat(cb.amount ?? "0"); break;
        case "stage": va = stageOrderMap.get(a.stageId) ?? 999; vb = stageOrderMap.get(b.stageId) ?? 999; break;
        case "probability": va = ca.probability ?? -1; vb = cb.probability ?? -1; break;
        case "assigned_to_name": va = ca.assigned_to_name ?? ""; vb = cb.assigned_to_name ?? ""; break;
        case "days_in_stage": va = ca.days_in_stage; vb = cb.days_in_stage; break;
        case "close_date": va = ca.close_date ?? "9999"; vb = cb.close_date ?? "9999"; break;
        default: va = ca.title; vb = cb.title;
      }
      if (typeof va === "number") return sortDir === "asc" ? va - vb : (vb as number) - va;
      return sortDir === "asc" ? va.localeCompare(vb as string) : (vb as string).localeCompare(va);
    });

    return filtered;
  }, [boardByStage, filters, sortCol, sortDir, stageOrderMap]);

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await api.exportOpportunitiesCsv(
        branchId ? { branch_id: branchId } : {},
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "oportunidades.csv";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("CSV exportado");
    } catch {
      toast.error("Error al exportar CSV");
    } finally {
      setExporting(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-2" aria-busy="true" aria-label="Cargando tabla">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex gap-3">
            {Array.from({ length: 6 }).map((_, j) => (
              <Skeleton key={j} className="h-9 flex-1 rounded-md" />
            ))}
          </div>
        ))}
      </div>
    );
  }

  function Th({ col, label, className }: { col: SortCol; label: string; className?: string }) {
    return (
      <TableHead className={cn("cursor-pointer select-none", className)} onClick={() => handleSort(col)}>
        <div className="flex items-center gap-1">
          {label}
          <SortIcon col={col} active={sortCol} dir={sortDir} />
        </div>
      </TableHead>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 h-8 text-xs"
          onClick={handleExport}
          disabled={exporting}
          aria-label="Exportar oportunidades a CSV"
        >
          <Download className="h-3.5 w-3.5" aria-hidden="true" />
          {exporting ? "Exportando…" : "Exportar CSV"}
        </Button>
      </div>

      {rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-2">
          <p className="text-sm text-muted-foreground font-medium">Sin resultados</p>
          <p className="text-xs text-muted-foreground">Ajusta los filtros para ver oportunidades</p>
        </div>
      ) : (
        <div className="rounded-xl border border-border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <Th col="title" label="Oportunidad" />
                <Th col="lead_name" label="Contacto" />
                <Th col="amount" label="Monto" className="text-right" />
                <Th col="stage" label="Etapa" />
                <Th col="probability" label="Prob." />
                <Th col="assigned_to_name" label="Vendedor" />
                <Th col="days_in_stage" label="Días" />
                <Th col="close_date" label="Cierre" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map(({ card, stageId }) => {
                const stageColor = stageColorMap.get(stageId);
                const stageName = stageNameMap.get(stageId) ?? "";
                const pct = card.probability ?? 0;
                const probClass = pct >= 70 ? "text-success" : pct >= 40 ? "text-warning" : "text-danger";
                return (
                  <TableRow
                    key={card.id}
                    className="cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => openDrawer(card.id)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && openDrawer(card.id)}
                    role="button"
                    aria-label={`Abrir detalle de ${card.title}`}
                  >
                    <TableCell className="font-medium max-w-[200px] truncate">
                      {card.title}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {card.lead_name ?? "—"}
                    </TableCell>
                    <TableCell className="text-right font-bold text-success tabular-nums">
                      {card.amount ? formatMXN(card.amount) : "—"}
                    </TableCell>
                    <TableCell>
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full",
                          !stageColor && "bg-primary/10 text-primary border border-primary/25",
                        )}
                        style={stageColor ? {
                          backgroundColor: `${stageColor}20`,
                          color: stageColor,
                          border: `1px solid ${stageColor}40`,
                        } : undefined}
                      >
                        {stageName}
                      </span>
                    </TableCell>
                    <TableCell>
                      {card.probability != null ? (
                        <span className={cn("text-sm font-semibold tabular-nums", probClass)}>
                          {card.probability}%
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {card.assigned_to_name ? (
                        <div className="flex items-center gap-2">
                          <span
                            className="inline-flex items-center justify-center h-6 w-6 rounded-full text-[10px] font-bold shrink-0 text-white"
                            style={{ backgroundColor: avatarColor(card.assigned_to) }}
                            aria-hidden="true"
                          >
                            {initials(card.assigned_to_name)}
                          </span>
                          <span className="text-sm truncate max-w-[100px]">{card.assigned_to_name}</span>
                        </div>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums text-sm">
                      {card.days_in_stage}d
                    </TableCell>
                    <TableCell className="text-sm tabular-nums text-muted-foreground">
                      {card.close_date
                        ? new Date(card.close_date + "T00:00:00").toLocaleDateString("es-MX", {
                            day: "2-digit",
                            month: "short",
                            year: "numeric",
                          })
                        : "—"}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
