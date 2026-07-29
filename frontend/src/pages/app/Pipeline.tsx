import { useMemo, useState } from "react";
import { Clock } from "lucide-react";
import { useTenantLabels } from "@/hooks/useTenantLabels";
import { PipelineHeader } from "@/components/pipeline/PipelineHeader";
import { KanbanBoard } from "@/components/pipeline/KanbanBoard";
import { DealsListView } from "@/components/pipeline/DealsListView";
import { NewDealDialog } from "@/components/pipeline/NewDealDialog";
import { LostReasonDialog } from "@/components/pipeline/LostReasonDialog";
import { DealDrawer } from "@/components/pipeline/DealDrawer";
import { type PipelineFiltersValue } from "@/components/pipeline/PipelineFilters";
import { AiAlertBanner } from "@/components/walix/AiAlertBanner";
import { PipelineSuggestionsPanel } from "@/components/pipeline/PipelineSuggestionsPanel";
import { BulkActionsBar } from "@/components/pipeline/BulkActionsBar";
import { PipelineManagerDialog } from "@/components/pipeline/PipelineManagerDialog";
import { usePipelinePrefs } from "@/lib/usePipelinePrefs";
import {
  usePipelines, useStages, useDeals, useContactsLite,
  type PipelineDeal, type PipelineStage,
} from "@/lib/queries/pipeline";

export default function Pipeline() {
  const { deal, deals: dealsLabel } = useTenantLabels();
  const [prefs, setPrefs] = usePipelinePrefs();

  const { data: pipelines = [] } = usePipelines();

  // Resolve active pipeline: prefs if still valid, else first is_default, else first
  const activePipelineId = useMemo(() => {
    if (prefs.pipelineId && pipelines.some((p) => p.id === prefs.pipelineId)) {
      return prefs.pipelineId;
    }
    return pipelines.find((p) => p.isDefault)?.id ?? pipelines[0]?.id ?? null;
  }, [prefs.pipelineId, pipelines]);

  const handleSelectPipeline = (id: string) => setPrefs({ ...prefs, pipelineId: id });

  const { data: stages = [], isLoading: stagesLoading } = useStages(activePipelineId);
  const { data: deals = [], isLoading: dealsLoading } = useDeals(activePipelineId);
  const { data: contacts = [] } = useContactsLite();

  // Filtros desde prefs (Date serializado como ISO)
  const filters: PipelineFiltersValue = useMemo(() => ({
    ownerName: prefs.filters.ownerName,
    amountMin: prefs.filters.amountMin,
    amountMax: prefs.filters.amountMax,
    closeBefore: prefs.filters.closeBefore ? new Date(prefs.filters.closeBefore) : undefined,
    source: prefs.filters.source,
    tag: prefs.filters.tag,
  }), [prefs.filters]);

  const setFilters = (v: PipelineFiltersValue) =>
    setPrefs({
      ...prefs,
      filters: {
        ownerName: v.ownerName,
        amountMin: v.amountMin,
        amountMax: v.amountMax,
        closeBefore: v.closeBefore ? v.closeBefore.toISOString() : null,
        source: v.source,
        tag: v.tag,
      },
    });

  const view = prefs.view;
  const setView = (v: "kanban" | "list") => setPrefs({ ...prefs, view: v });
  const search = prefs.search;
  const setSearch = (v: string) => setPrefs({ ...prefs, search: v });

  const [managerOpen, setManagerOpen] = useState(false);
  const [newDealOpen, setNewDealOpen] = useState(false);
  const [newDealStage, setNewDealStage] = useState<string | null>(null);
  const [lostDeal, setLostDeal] = useState<PipelineDeal | null>(null);
  const [openDeal, setOpenDeal] = useState<PipelineDeal | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const lostStage = stages.find((s) => s.isLost) ?? null;

  // Resolución de contacto (nombre/color) desde el módulo de leads.
  const contactById = useMemo(() => new Map(contacts.map((c) => [c.id, c])), [contacts]);
  const contactName = (id: string | null) => {
    if (!id) return undefined;
    const c = contactById.get(id);
    return c ? `${c.name}${c.lastName ? " " + c.lastName : ""}` : undefined;
  };
  const contactColor = (id: string | null) => (id ? contactById.get(id)?.avatarColor ?? null : null);

  // La fecha de última actividad viene en el propio deal (derivada por el backend).
  const lastActivityByContact = useMemo(() => {
    const m = new Map<string, string | null>();
    for (const d of deals) if (d.contactId) m.set(d.contactId, d.contactLastActivityAt);
    return m;
  }, [deals]);
  const contactLastActivityAt = (id: string | null) => (id ? lastActivityByContact.get(id) ?? null : null);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const stageIds = new Set(stages.map((s) => s.id));
    return deals.filter((d) => {
      if (d.stageId && !stageIds.has(d.stageId)) return false;
      if (filters.ownerName !== "all" && d.ownerName !== filters.ownerName) return false;
      if (filters.amountMin && d.amount < Number(filters.amountMin)) return false;
      if (filters.amountMax && d.amount > Number(filters.amountMax)) return false;
      if (filters.closeBefore && d.expectedCloseDate && new Date(d.expectedCloseDate) > filters.closeBefore) return false;
      if (filters.source !== "all" && d.source !== filters.source) return false;
      if (filters.tag && !d.name.toLowerCase().includes(filters.tag.toLowerCase()) && !(d.notes ?? "").toLowerCase().includes(filters.tag.toLowerCase())) return false;
      if (q) {
        const cName = contactName(d.contactId)?.toLowerCase() ?? "";
        const hay = `${d.name} ${d.notes ?? ""} ${cName}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [deals, filters, search, contactById, stages]);

  const activeDeals = filtered.filter((d) => !d.isWon && !d.isLost);
  const totalAmount = activeDeals.reduce((s, d) => s + d.amount, 0);
  const weightedAmount = activeDeals.reduce((s, d) => s + (d.amount * d.probability) / 100, 0);

  // Stale: >10 días sin actividad reciente del contacto / sin updates
  const staleDeals = useMemo(() => {
    const now = Date.now();
    return activeDeals.filter((d) => {
      const ref = (d.contactId ? lastActivityByContact.get(d.contactId) : null) ?? d.updatedAt;
      return (now - new Date(ref).getTime()) / 86_400_000 > 10;
    });
  }, [activeDeals, lastActivityByContact]);
  const staleAmount = staleDeals.reduce((s, d) => s + d.amount, 0);

  const now = new Date();
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  const startOfPrevMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);

  const closingThisMonth = activeDeals
    .filter((d) => d.expectedCloseDate && new Date(d.expectedCloseDate) >= startOfMonth && new Date(d.expectedCloseDate) < endOfMonth)
    .reduce((s, d) => s + d.amount, 0);

  const closingPrevMonth = filtered
    .filter((d) => d.expectedCloseDate && new Date(d.expectedCloseDate) >= startOfPrevMonth && new Date(d.expectedCloseDate) < startOfMonth)
    .reduce((s, d) => s + d.amount, 0);

  const closingDeltaPct =
    closingPrevMonth > 0 ? ((closingThisMonth - closingPrevMonth) / closingPrevMonth) * 100 : null;

  function openNewDeal(stage?: PipelineStage) {
    setNewDealStage(stage?.id ?? null);
    setNewDealOpen(true);
  }

  // Abre el DealDrawer (14C.3). El deal mostrado se re-deriva de la lista fresca por id,
  // para que tras editar se vean los datos actualizados sin cerrar el drawer.
  const onOpenDeal = (deal: PipelineDeal) => setOpenDeal(deal);
  const openDealFresh = openDeal ? (deals.find((d) => d.id === openDeal.id) ?? openDeal) : null;

  if (stagesLoading || dealsLoading) {
    return <div className="py-20 text-center text-sm text-muted-foreground">Cargando pipeline…</div>;
  }

  return (
    <div className="space-y-4 max-w-full">
      <PipelineHeader
        view={view}
        onView={setView}
        filters={filters}
        onFilters={setFilters}
        search={search}
        onSearch={setSearch}
        onNew={() => openNewDeal()}
        totalAmount={totalAmount}
        weightedAmount={weightedAmount}
        closingThisMonth={closingThisMonth}
        closingDeltaPct={closingDeltaPct}
        activeCount={activeDeals.length}
        pipelines={pipelines}
        activePipelineId={activePipelineId}
        onSelectPipeline={handleSelectPipeline}
        onManage={() => setManagerOpen(true)}
      />

      {staleDeals.length > 0 && (
        <AiAlertBanner
          variant="warning"
          icon={<Clock className="h-4 w-4" />}
          title={`${staleDeals.length} ${staleDeals.length === 1 ? deal : dealsLabel} sin actividad hace más de 10 días`}
          description={`Suman ${new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 }).format(staleAmount)} en pipeline. Revísalos antes de que se enfríen.`}
        />
      )}

      <PipelineSuggestionsPanel />

      {deals.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card py-16 px-6 text-center">
          <h3 className="font-semibold text-lg">Crea tu primera {deal.toLowerCase()} y empieza a cerrar</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Organiza tus {dealsLabel.toLowerCase()} en etapas y arrástralas entre columnas.
          </p>
          <button
            onClick={() => openNewDeal()}
            className="mt-4 inline-flex items-center gap-1 rounded-md bg-primary text-primary-foreground px-3 py-2 text-sm font-medium hover:bg-primary/90"
          >
            + Nueva {deal}
          </button>
        </div>
      ) : view === "kanban" ? (
        <KanbanBoard
          stages={stages}
          deals={filtered}
          contactName={contactName}
          contactColor={contactColor}
          contactLastActivityAt={contactLastActivityAt}
          onOpenDeal={onOpenDeal}
          onAddDeal={openNewDeal}
          onRequestLost={setLostDeal}
        />
      ) : (
        <DealsListView
          deals={filtered}
          contactName={contactName}
          onOpenDeal={onOpenDeal}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
        />
      )}

      <NewDealDialog
        open={newDealOpen}
        onOpenChange={setNewDealOpen}
        stages={stages}
        defaultStageId={newDealStage}
      />

      <LostReasonDialog
        open={!!lostDeal}
        deal={lostDeal}
        lostStage={lostStage}
        onClose={() => setLostDeal(null)}
      />

      <DealDrawer
        deal={openDealFresh}
        stages={stages}
        open={!!openDeal}
        onClose={() => setOpenDeal(null)}
        contactName={openDealFresh ? contactName(openDealFresh.contactId) : undefined}
      />

      <BulkActionsBar
        selectedIds={[...selectedIds]}
        stages={stages}
        onClear={() => setSelectedIds(new Set())}
      />

      <PipelineManagerDialog
        open={managerOpen}
        onClose={() => setManagerOpen(false)}
        onSelect={(id) => {
          setPrefs({ ...prefs, pipelineId: id });
          setManagerOpen(false);
        }}
      />
    </div>
  );
}

/* FASE 2 (removido): multi-pipeline (usePipelines/PipelineManagerDialog), DealDrawer,
   QuickTaskDialog, BulkActionsBar, AiInsightsPanel, sugerencias IA, tasks/unread,
   EmptyState/EmptyIllustration (reemplazado por bloque inline). */
