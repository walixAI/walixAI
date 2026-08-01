import { Filter, X } from "lucide-react";
import { format } from "date-fns";
import { es } from "date-fns/locale";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Calendar } from "@/components/ui/calendar";
import { useTenantUsers } from "@/lib/queries/tenantUsers";
import { cn } from "@/lib/utils";

export interface PipelineFiltersValue {
  ownerName: string | "all";
  amountMin: string;
  amountMax: string;
  closeBefore: Date | undefined;
  source: string | "all";
  tag: string;
}

export const emptyFilters: PipelineFiltersValue = {
  ownerName: "all", amountMin: "", amountMax: "", closeBefore: undefined, source: "all", tag: "",
};

const sources = ["WhatsApp", "Formulario web", "Referido", "Manual"];

interface Props {
  value: PipelineFiltersValue;
  onChange: (v: PipelineFiltersValue) => void;
}

export function PipelineFilters({ value, onChange }: Props) {
  const { data: sellers = [] } = useTenantUsers();
  const activeCount =
    (value.ownerName !== "all" ? 1 : 0) +
    (value.amountMin ? 1 : 0) +
    (value.amountMax ? 1 : 0) +
    (value.closeBefore ? 1 : 0) +
    (value.source !== "all" ? 1 : 0) +
    (value.tag ? 1 : 0);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-9">
          <Filter className="h-3.5 w-3.5" /> Filtros
          {activeCount > 0 && (
            <span className="ml-1 bg-primary text-primary-foreground text-[10px] rounded-full h-4 min-w-4 px-1 grid place-items-center font-bold">
              {activeCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[320px]" align="end">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">Filtros</h4>
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => onChange(emptyFilters)}>
              <X className="h-3 w-3" /> Limpiar
            </Button>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Vendedor</Label>
            <Select value={value.ownerName} onValueChange={(v) => onChange({ ...value, ownerName: v as any })}>
              <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {sellers.map((s) => <SelectItem key={s.id} value={s.name}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Monto mín.</Label>
              <Input className="h-8" type="number" inputMode="numeric" value={value.amountMin} onChange={(e) => onChange({ ...value, amountMin: e.target.value })} placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Monto máx.</Label>
              <Input className="h-8" type="number" inputMode="numeric" value={value.amountMax} onChange={(e) => onChange({ ...value, amountMax: e.target.value })} placeholder="∞" />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Cierre antes de</Label>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className={cn("h-8 w-full justify-start font-normal", !value.closeBefore && "text-muted-foreground")}>
                  {value.closeBefore ? format(value.closeBefore, "PPP", { locale: es }) : "Cualquier fecha"}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar mode="single" selected={value.closeBefore} onSelect={(d) => onChange({ ...value, closeBefore: d })} className="p-3 pointer-events-auto" />
              </PopoverContent>
            </Popover>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Fuente</Label>
            <Select value={value.source} onValueChange={(v) => onChange({ ...value, source: v as any })}>
              <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                {sources.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Etiqueta del deal</Label>
            <Input className="h-8" value={value.tag} onChange={(e) => onChange({ ...value, tag: e.target.value })} placeholder="ej. premium" />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
