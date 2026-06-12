import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/lib/api";
import {
  getContacts,
  createContact,
  bulkContacts,
  exportContactsCsv,
  type ContactFilters,
  type ContactRow,
} from "@/lib/queries/contacts";
import { getTags } from "@/lib/queries/tags";
import { ContactsPageHeader } from "@/components/contacts/ContactsPageHeader";
import { ContactsFilters } from "@/components/contacts/ContactsFilters";
import { ContactsListView } from "@/components/contacts/ContactsListView";
import { ContactsKanbanView } from "@/components/contacts/ContactsKanbanView";
import { ContactsCardsView } from "@/components/contacts/ContactsCardsView";
import { BulkActionsInline } from "@/components/contacts/BulkActionsInline";
import { ContactImportModal } from "@/components/contacts/ContactImportModal";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ViewMode } from "@/components/contacts/ContactsViewToggle";

const VIEW_KEY = "walix-contacts-view";

// ── URL ↔ filter serialization ────────────────────────────────────────────────

function filtersFromSearch(sp: URLSearchParams): ContactFilters {
  const f: ContactFilters = {};
  const q = sp.get("q"); if (q) f.q = q;
  const status = sp.getAll("status") as ContactFilters["status"]; if (status.length) f.status = status;
  const source = sp.getAll("source"); if (source.length) f.source = source;
  const tag = sp.getAll("tag"); if (tag.length) f.tag = tag;
  const assigned = sp.getAll("assigned"); if (assigned.length) f.assigned = assigned;
  const dateFrom = sp.get("dateFrom"); if (dateFrom) f.dateFrom = dateFrom;
  const dateTo = sp.get("dateTo"); if (dateTo) f.dateTo = dateTo;
  const sort = sp.get("sort") as ContactFilters["sort"]; if (sort) f.sort = sort;
  const order = sp.get("order") as ContactFilters["order"]; if (order) f.order = order;
  const page = sp.get("page"); if (page) f.page = Number(page);
  return f;
}

function filtersToSearch(f: ContactFilters): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.q) sp.set("q", f.q);
  f.status?.forEach((s) => sp.append("status", s));
  f.source?.forEach((s) => sp.append("source", s));
  f.tag?.forEach((t) => sp.append("tag", t));
  f.assigned?.forEach((a) => sp.append("assigned", a));
  if (f.dateFrom) sp.set("dateFrom", f.dateFrom);
  if (f.dateTo) sp.set("dateTo", f.dateTo);
  if (f.sort) sp.set("sort", f.sort);
  if (f.order) sp.set("order", f.order);
  if (f.page && f.page > 1) sp.set("page", String(f.page));
  return sp;
}

function countActiveFilters(f: ContactFilters): number {
  let n = 0;
  if (f.status?.length) n++;
  if (f.source?.length) n++;
  if (f.tag?.length) n++;
  if (f.assigned?.length) n++;
  if (f.dateFrom || f.dateTo) n++;
  if (f.sort) n++;
  return n;
}

// ── Create contact form ───────────────────────────────────────────────────────

interface CreateFormData {
  phone: string;
  name: string;
  lastName: string;
  company: string;
  prospectionSource: string;
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ContactsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  // View mode (persisted in localStorage)
  const [viewMode, setViewMode] = useState<ViewMode>(
    () => (localStorage.getItem(VIEW_KEY) as ViewMode | null) ?? "list",
  );
  const handleViewChange = (m: ViewMode) => {
    setViewMode(m);
    localStorage.setItem(VIEW_KEY, m);
  };

  // Filters from URL
  const [filters, setFilters] = useState<ContactFilters>(() => filtersFromSearch(searchParams));
  const [filtersOpen, setFiltersOpen] = useState(false);

  // Search input with 300ms debounce
  const [searchInput, setSearchInput] = useState(filters.q ?? "");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleSearchChange = useCallback((q: string) => {
    setSearchInput(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setFilters((f) => ({ ...f, q: q || undefined, page: 1 }));
    }, 300);
  }, []);

  // Sync filters → URL
  useEffect(() => {
    setSearchParams(filtersToSearch(filters), { replace: true });
  }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps

  const updateFilters = useCallback((partial: Partial<ContactFilters>) => {
    setFilters((f) => ({ ...f, ...partial }));
  }, []);

  const page = filters.page ?? 1;
  const queryKey = useMemo(() => ["contacts", filters], [filters]);

  // Contacts query
  const { data, isLoading, isFetching } = useQuery({
    queryKey,
    queryFn: () => getContacts(filters),
    staleTime: 30_000,
  });

  // Team
  const branchId = user?.branch_id ?? "";
  const { data: team = [] } = useQuery({
    queryKey: ["team", branchId],
    queryFn: () => api.getTeam(branchId),
    enabled: Boolean(branchId),
    staleTime: 5 * 60_000,
  });

  // Tags
  const { data: tags = [] } = useQuery({
    queryKey: ["tags"],
    queryFn: getTags,
    staleTime: 5 * 60_000,
  });

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((s) => {
      const next = new Set(s);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  }, []);
  const toggleAll = useCallback((ids: string[]) => {
    setSelectedIds((s) => {
      const allSelected = ids.every((id) => s.has(id));
      if (allSelected) {
        const next = new Set(s);
        ids.forEach((id) => next.delete(id));
        return next;
      }
      return new Set([...s, ...ids]);
    });
  }, []);

  // Export
  const [isExporting, setIsExporting] = useState(false);
  const handleExport = useCallback(async () => {
    setIsExporting(true);
    try {
      await exportContactsCsv(filters);
      toast.success("CSV descargado correctamente");
    } catch (e: unknown) {
      toast.error("Error al exportar", { description: e instanceof Error ? e.message : String(e) });
    } finally {
      setIsExporting(false);
    }
  }, [filters]);

  // Import modal
  const [importModalOpen, setImportModalOpen] = useState(false);

  // Bulk delete
  const handleBulkDelete = useCallback(async (ids: string[]) => {
    await bulkContacts("delete", ids);
    toast.success(`${ids.length} contacto${ids.length !== 1 ? "s" : ""} eliminado${ids.length !== 1 ? "s" : ""}`);
    setSelectedIds(new Set());
    qc.invalidateQueries({ queryKey: ["contacts"] });
  }, [qc]);

  // Create contact sheet
  const [createOpen, setCreateOpen] = useState(false);
  const { register, handleSubmit, reset, setValue, watch, formState: { isSubmitting } } = useForm<CreateFormData>({
    defaultValues: { phone: "", name: "", lastName: "", company: "", prospectionSource: "manual" },
  });

  const createMutation = useMutation({
    mutationFn: (d: CreateFormData) =>
      createContact({
        phone: d.phone,
        name: d.name || null,
        lastName: d.lastName || null,
        company: d.company || null,
        prospectionSource: d.prospectionSource,
      }),
    onSuccess: () => {
      toast.success("Contacto creado");
      reset();
      setCreateOpen(false);
      qc.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (e: Error) => toast.error("Error al crear contacto", { description: e.message }),
  });

  const activeFilterCount = countActiveFilters(filters);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <ContactsPageHeader
        total={data?.total ?? 0}
        isLoading={isLoading}
        viewMode={viewMode}
        onViewChange={handleViewChange}
        activeFilterCount={activeFilterCount}
        onNewContact={() => setCreateOpen(true)}
        onExport={handleExport}
        onImportFile={() => setImportModalOpen(true)}
        isExporting={isExporting}
      />

      <ContactsFilters
        open={filtersOpen}
        onToggle={() => setFiltersOpen((v) => !v)}
        searchValue={searchInput}
        onSearchChange={handleSearchChange}
        filters={filters}
        onChange={updateFilters}
        team={team}
        tags={tags}
        activeCount={activeFilterCount}
      />

      <div className="flex-1 overflow-auto p-4">
        {viewMode === "list" && (
          <ContactsListView
            data={data}
            isLoading={isLoading || isFetching}
            page={page}
            onPageChange={(p) => updateFilters({ page: p })}
            selectedIds={selectedIds}
            onToggleSelect={toggleSelect}
            onToggleAll={toggleAll}
          />
        )}

        {viewMode === "kanban" && (
          <ContactsKanbanView
            data={data}
            isLoading={isLoading}
            filters={filters}
            queryKey={queryKey}
            onCardClick={(c: ContactRow) => navigate(`/contacts/${c.id}`)}
          />
        )}

        {viewMode === "cards" && (
          <ContactsCardsView
            contacts={data?.items ?? []}
            isLoading={isLoading}
            onEdit={(c: ContactRow) => navigate(`/contacts/${c.id}`)}
          />
        )}
      </div>

      {selectedIds.size > 0 && (
        <BulkActionsInline
          selectedIds={selectedIds}
          onClear={() => setSelectedIds(new Set())}
          onDelete={handleBulkDelete}
          onExport={(ids) =>
            exportContactsCsv({ ...filters, assigned: ids })
              .then(() => toast.success("CSV exportado"))
              .catch((e: Error) => toast.error(e.message))
          }
        />
      )}

      {/* Create contact sheet */}
      <Sheet open={createOpen} onOpenChange={setCreateOpen}>
        <SheetContent side="right" className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Nuevo contacto</SheetTitle>
          </SheetHeader>

          <form
            onSubmit={handleSubmit((d) => createMutation.mutate(d))}
            className="flex flex-col gap-4 mt-4"
          >
            <div className="space-y-1.5">
              <Label>Teléfono WhatsApp *</Label>
              <Input
                {...register("phone", { required: true })}
                placeholder="+521234567890"
                className="font-mono"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Nombre</Label>
                <Input {...register("name")} placeholder="Juan" />
              </div>
              <div className="space-y-1.5">
                <Label>Apellido</Label>
                <Input {...register("lastName")} placeholder="García" />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Empresa</Label>
              <Input {...register("company")} placeholder="ACME S.A." />
            </div>

            <div className="space-y-1.5">
              <Label>Fuente</Label>
              <Select
                value={watch("prospectionSource")}
                onValueChange={(v) => setValue("prospectionSource", v)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="whatsapp_inbound">WhatsApp</SelectItem>
                  <SelectItem value="web_form">Formulario web</SelectItem>
                  <SelectItem value="referral">Referido</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <SheetFooter className="mt-2">
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={isSubmitting || createMutation.isPending}>
                {createMutation.isPending ? "Creando…" : "Crear contacto"}
              </Button>
            </SheetFooter>
          </form>
        </SheetContent>
      </Sheet>

      {/* Import modal */}
      <ContactImportModal
        open={importModalOpen}
        onClose={() => setImportModalOpen(false)}
        onImportComplete={(count) => {
          setImportModalOpen(false);
          qc.invalidateQueries({ queryKey: ["contacts"] });
          toast.success(`${count} contactos importados correctamente`);
        }}
      />
    </div>
  );
}
