import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useOpportunityStore } from "@/stores/opportunityStore";
import { PipelineHeader } from "./components/PipelineHeader";
import { ForecastBar } from "./components/ForecastBar";
import { StaleBanner } from "./components/StaleBanner";
import { OppKanbanBoard } from "./components/KanbanBoard";
import { OpportunityTable } from "./components/OpportunityTable";
import { OpportunityDrawer } from "./components/OpportunityDrawer";
import { InsightsDrawer } from "./components/InsightsDrawer";
import { BulkActionBar } from "./components/BulkActionBar";
import { NuevaOportunidadModal } from "./components/modals/NuevaOportunidadModal";
import { MarcarPerdidoModal } from "./components/modals/MarcarPerdidoModal";
import { NuevaTareaModal } from "./components/modals/NuevaTareaModal";
import { StickyFooter } from "./components/StickyFooter";

export default function PipelinePage() {
  const { user } = useAuth();
  const { fetchAll, forecast, stale, view, openNewOppModal } = useOpportunityStore();
  const [insightsOpen, setInsightsOpen] = useState(false);

  const branchId = user?.branch_id ?? undefined;

  useEffect(() => {
    fetchAll(branchId);
  }, [branchId, fetchAll]);

  return (
    <div className="h-full flex flex-col gap-3 pb-12">
      <PipelineHeader
        onInsightsAI={() => setInsightsOpen(true)}
        onNewOpportunity={() => openNewOppModal()}
      />

      <ForecastBar forecast={forecast} />

      {stale && stale.count > 0 && <StaleBanner stale={stale} />}

      <div className="flex-1 overflow-x-auto">
        {view === "kanban" ? (
          <OppKanbanBoard onNewOpportunity={(stageId) => openNewOppModal(stageId)} />
        ) : (
          <div className="px-1 overflow-x-auto">
            <OpportunityTable />
          </div>
        )}
      </div>

      <StickyFooter />

      {/* Floating bulk bar — sits above StickyFooter */}
      <BulkActionBar />

      {/* Drawers */}
      <InsightsDrawer open={insightsOpen} onClose={() => setInsightsOpen(false)} />
      <OpportunityDrawer />

      {/* Modals */}
      <NuevaOportunidadModal />
      <MarcarPerdidoModal />
      <NuevaTareaModal />
    </div>
  );
}
