import { useMemo, useState } from "react";
import { ArrowUpDown, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  daysSince, formatMXN, type PipelineDeal,
} from "@/lib/queries/pipeline";
import { cn } from "@/lib/utils";

interface Props {
  deals: PipelineDeal[];
  contactName: (id: string | null) => string | undefined;
  onOpenDeal: (deal: PipelineDeal) => void;
}

type SortKey = "name" | "contact" | "amount" | "stage" | "probability" | "owner" | "days" | "close";

export function DealsListView({ deals, contactName, onOpenDeal }: Props) {
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "amount", dir: "desc" });

  const sorted = useMemo(() => {
    const arr = [...deals];
    arr.sort((a, b) => {
      const dir = sort.dir === "asc" ? 1 : -1;
      switch (sort.key) {
        case "name": return a.name.localeCompare(b.name) * dir;
        case "contact": return (contactName(a.contactId) ?? "").localeCompare(contactName(b.contactId) ?? "") * dir;
        case "amount": return (a.amount - b.amount) * dir;
        case "stage": return a.stageName.localeCompare(b.stageName) * dir;
        case "probability": return (a.probability - b.probability) * dir;
        case "owner": return a.ownerName.localeCompare(b.ownerName) * dir;
        case "days": return (daysSince(a.updatedAt) - daysSince(b.updatedAt)) * dir;
        case "close": return ((a.expectedCloseDate ?? "") > (b.expectedCloseDate ?? "") ? 1 : -1) * dir;
      }
    });
    return arr;
  }, [deals, sort, contactName]);

  function toggle(k: SortKey) {
    setSort((s) => s.key === k ? { key: k, dir: s.dir === "asc" ? "desc" : "asc" } : { key: k, dir: "desc" });
  }

  function exportCsv() {
    const headers = ["Deal", "Contacto", "Monto MXN", "Etapa", "Probabilidad", "Vendedor", "Días en etapa", "Fecha cierre"];
    const rows = sorted.map((d) => [
      d.name,
      contactName(d.contactId) ?? "",
      d.amount.toString(),
      d.stageName,
      `${d.probability}%`,
      d.ownerName,
      daysSince(d.updatedAt).toString(),
      d.expectedCloseDate ?? "",
    ]);
    const csv = [headers, ...rows].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "pipeline.csv"; a.click();
    URL.revokeObjectURL(url);
  }

  const SortBtn = ({ k, label }: { k: SortKey; label: string }) => (
    <button onClick={() => toggle(k)} className="inline-flex items-center gap-1 hover:text-foreground transition-colors">
      {label} <ArrowUpDown className={cn("h-3 w-3", sort.key === k ? "text-primary" : "text-muted-foreground/60")} />
    </button>
  );

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={exportCsv}>
          <Download className="h-3.5 w-3.5" /> Exportar CSV
        </Button>
      </div>
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead><SortBtn k="name" label="Deal" /></TableHead>
              <TableHead><SortBtn k="contact" label="Contacto" /></TableHead>
              <TableHead className="text-right"><SortBtn k="amount" label="Monto" /></TableHead>
              <TableHead><SortBtn k="stage" label="Etapa" /></TableHead>
              <TableHead><SortBtn k="probability" label="Prob." /></TableHead>
              <TableHead><SortBtn k="owner" label="Vendedor" /></TableHead>
              <TableHead><SortBtn k="days" label="Días" /></TableHead>
              <TableHead><SortBtn k="close" label="Cierre" /></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((d) => (
              <TableRow key={d.id} className="cursor-pointer" onClick={() => onOpenDeal(d)}>
                <TableCell className="font-medium">{d.name}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{contactName(d.contactId) ?? "—"}</TableCell>
                <TableCell className="text-right font-semibold text-success">{formatMXN(d.amount)}</TableCell>
                <TableCell className="text-sm">{d.stageName}</TableCell>
                <TableCell className="text-sm">{d.probability}%</TableCell>
                <TableCell>
                  <div className="flex items-center gap-1.5">
                    <Avatar className="h-5 w-5">
                      <AvatarFallback className="text-[9px] text-white" style={{ backgroundColor: d.ownerColor }}>
                        {d.ownerInitials}
                      </AvatarFallback>
                    </Avatar>
                    <span className="text-xs">{d.ownerName}</span>
                  </div>
                </TableCell>
                <TableCell className="text-sm">{daysSince(d.updatedAt)}d</TableCell>
                <TableCell className="text-sm">{d.expectedCloseDate ? new Date(d.expectedCloseDate).toLocaleDateString("es-MX") : "—"}</TableCell>
              </TableRow>
            ))}
            {sorted.length === 0 && (
              <TableRow>
                <TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-10">Sin resultados</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
