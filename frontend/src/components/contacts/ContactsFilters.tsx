import { Search, X, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ContactStatusBadge } from "@/components/ui/ContactStatusBadge";
import type { LeadStatus, ContactFilters, TagRow } from "@/lib/queries/contacts";
import type { TeamMemberOut } from "@/lib/api";
import { useTenantLabels } from "@/hooks/useTenantLabels";

const SOURCES: { value: string; label: string }[] = [
  { value: "whatsapp_inbound", label: "WhatsApp" },
  { value: "web_form",         label: "Formulario web" },
  { value: "referral",         label: "Referido" },
  { value: "manual",           label: "Manual" },
];

const SORT_OPTIONS: { value: ContactFilters["sort"]; label: string }[] = [
  { value: "name",         label: "Nombre" },
  { value: "company",      label: "Empresa" },
  { value: "status",       label: "Estado" },
  { value: "lastActivity", label: "Última actividad" },
];

interface ContactsFiltersProps {
  open: boolean;
  onToggle: () => void;
  searchValue: string;
  onSearchChange: (q: string) => void;
  filters: ContactFilters;
  onChange: (partial: Partial<ContactFilters>) => void;
  team: TeamMemberOut[];
  tags: TagRow[];
  activeCount: number;
}

function toggleArrayItem<T>(arr: T[] | undefined, item: T): T[] {
  const current = arr ?? [];
  return current.includes(item)
    ? current.filter((x) => x !== item)
    : [...current, item];
}

export function ContactsFilters({
  open,
  onToggle,
  searchValue,
  onSearchChange,
  filters,
  onChange,
  team,
  tags,
  activeCount,
}: ContactsFiltersProps) {
  const { statuses, searchEntityPlaceholder } = useTenantLabels();
  return (
    <div className="border-b border-border bg-background">
      {/* Always-visible search bar */}
      <div className="flex items-center gap-2 px-4 py-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <Input
            data-testid="contacts-search"
            placeholder={searchEntityPlaceholder}
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
          {searchValue && (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        <Button
          data-testid="filters-toggle-btn"
          variant="outline"
          size="sm"
          onClick={onToggle}
          className="h-8 text-xs gap-1.5"
        >
          {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          Filtros
          {activeCount > 0 && (
            <span className="ml-0.5 inline-flex items-center justify-center h-4 w-4 rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
              {activeCount}
            </span>
          )}
        </Button>

        {activeCount > 0 && (
          <Button
            data-testid="clear-filters-btn"
            variant="ghost"
            size="sm"
            onClick={() => onChange({ status: undefined, source: undefined, tag: undefined, assigned: undefined, dateFrom: undefined, dateTo: undefined, sort: undefined, order: undefined })}
            className="h-8 text-xs text-muted-foreground"
          >
            Limpiar filtros
          </Button>
        )}
      </div>

      {/* Expanded filter panel */}
      {open && (
        <div data-testid="filters-panel" className="px-4 pb-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 border-t border-border pt-3">

          {/* Status */}
          <div className="space-y-1.5">
            <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Estado</Label>
            <div className="space-y-1">
              {statuses.map((s) => (
                <label key={s.key} className="flex items-center gap-2 cursor-pointer group">
                  <Checkbox
                    data-testid={`status-filter-${s.key}`}
                    checked={filters.status?.includes(s.key as LeadStatus) ?? false}
                    onCheckedChange={() =>
                      onChange({ status: toggleArrayItem(filters.status, s.key as LeadStatus), page: 1 })
                    }
                  />
                  <ContactStatusBadge status={s.key} />
                </label>
              ))}
            </div>
          </div>

          {/* Source */}
          <div className="space-y-1.5">
            <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Fuente</Label>
            <div className="space-y-1">
              {SOURCES.map((src) => (
                <label key={src.value} className="flex items-center gap-2 cursor-pointer">
                  <Checkbox
                    checked={filters.source?.includes(src.value) ?? false}
                    onCheckedChange={() =>
                      onChange({ source: toggleArrayItem(filters.source, src.value), page: 1 })
                    }
                  />
                  <span className="text-sm">{src.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Assigned user */}
          <div className="space-y-1.5">
            <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Vendedor</Label>
            {team.length === 0 ? (
              <p className="text-xs text-muted-foreground">Sin equipo cargado</p>
            ) : (
              <div className="space-y-1 max-h-36 overflow-y-auto">
                {team.map((member) => (
                  <label key={member.id} className="flex items-center gap-2 cursor-pointer">
                    <Checkbox
                      checked={filters.assigned?.includes(member.id) ?? false}
                      onCheckedChange={() =>
                        onChange({ assigned: toggleArrayItem(filters.assigned, member.id), page: 1 })
                      }
                    />
                    <span className="text-sm truncate">{member.name}</span>
                  </label>
                ))}
              </div>
            )}

            {/* Tags */}
            <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mt-3 block">Etiquetas</Label>
            {tags.length === 0 ? (
              <p className="text-xs text-muted-foreground">Sin etiquetas</p>
            ) : (
              <div className="flex flex-wrap gap-1.5 mt-1">
                {tags.map((tag) => {
                  const active = filters.tag?.includes(tag.id) ?? false;
                  return (
                    <button
                      key={tag.id}
                      type="button"
                      onClick={() =>
                        onChange({ tag: toggleArrayItem(filters.tag, tag.id), page: 1 })
                      }
                      className={cn(
                        "px-2 py-0.5 rounded-full text-[10px] font-medium border transition-opacity",
                        active ? "opacity-100 ring-1 ring-offset-1" : "opacity-60 hover:opacity-100",
                      )}
                      style={{
                        backgroundColor: `${tag.color ?? "#6366f1"}20`,
                        borderColor: `${tag.color ?? "#6366f1"}60`,
                        color: tag.color ?? "#6366f1",
                        ringColor: tag.color ?? "#6366f1",
                      }}
                    >
                      {tag.name}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Date range + sort */}
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Fecha creación</Label>
              <div className="flex flex-col gap-1.5">
                <Input
                  type="date"
                  value={filters.dateFrom ?? ""}
                  onChange={(e) => onChange({ dateFrom: e.target.value || undefined, page: 1 })}
                  className="h-8 text-xs"
                />
                <Input
                  type="date"
                  value={filters.dateTo ?? ""}
                  onChange={(e) => onChange({ dateTo: e.target.value || undefined, page: 1 })}
                  className="h-8 text-xs"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Ordenar por</Label>
              <Select
                value={filters.sort ?? "__none__"}
                onValueChange={(v) => onChange({ sort: v === "__none__" ? undefined : v as ContactFilters["sort"] })}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="Sin orden" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Sin orden</SelectItem>
                  {SORT_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value!}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {filters.sort && (
                <div className="flex gap-1.5">
                  {(["asc", "desc"] as const).map((dir) => (
                    <button
                      key={dir}
                      type="button"
                      onClick={() => onChange({ order: dir })}
                      className={cn(
                        "flex-1 text-xs py-1 rounded border transition-colors",
                        filters.order === dir
                          ? "bg-primary text-primary-foreground border-primary"
                          : "border-border hover:bg-muted",
                      )}
                    >
                      {dir === "asc" ? "↑ Asc" : "↓ Desc"}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
