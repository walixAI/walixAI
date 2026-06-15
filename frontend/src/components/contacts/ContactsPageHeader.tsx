import { Bookmark, Download, Loader2, Plus, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ContactsViewToggle, type ViewMode } from "./ContactsViewToggle";
import { useTenantLabels } from "@/hooks/useTenantLabels";

interface ContactsPageHeaderProps {
  total: number;
  isLoading: boolean;
  viewMode: ViewMode;
  onViewChange: (mode: ViewMode) => void;
  activeFilterCount: number;
  onNewContact: () => void;
  onExport: () => void;
  onImportFile: () => void;
  isExporting: boolean;
  onSaveView: () => void;
}

export function ContactsPageHeader({
  total,
  isLoading,
  viewMode,
  onViewChange,
  activeFilterCount,
  onNewContact,
  onExport,
  onImportFile,
  isExporting,
  onSaveView,
}: ContactsPageHeaderProps) {
  const { entities, newEntityLabel, totalLabel } = useTenantLabels();
  const saveViewBtn = (
    <Button
      data-testid="save-view-btn"
      variant="outline"
      size="sm"
      className="h-8 text-xs gap-1.5"
      onClick={onSaveView}
      disabled={activeFilterCount === 0}
    >
      <Bookmark className="h-3.5 w-3.5" />
      Guardar vista
    </Button>
  );

  return (
    <div
      data-testid="contacts-header"
      className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border bg-background shrink-0"
    >
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold leading-none">{entities}</h1>
        {!isLoading && (
          <span className="text-sm text-muted-foreground tabular-nums">
            {totalLabel(total)}
          </span>
        )}
        {activeFilterCount > 0 && (
          <span
            data-testid="filter-count-badge"
            className="inline-flex items-center justify-center h-5 min-w-[20px] px-1 rounded-full bg-primary/10 text-primary text-[10px] font-bold"
          >
            {activeFilterCount} filtro{activeFilterCount !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <ContactsViewToggle value={viewMode} onChange={onViewChange} />

        {activeFilterCount === 0 ? (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>{saveViewBtn}</TooltipTrigger>
              <TooltipContent>
                Aplica filtros primero para guardar una vista
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : (
          saveViewBtn
        )}

        <Button
          data-testid="import-csv-btn"
          variant="outline"
          size="sm"
          className="h-8 text-xs gap-1.5"
          onClick={onImportFile}
        >
          <Upload className="h-3.5 w-3.5" />
          Importar CSV
        </Button>

        <Button
          variant="outline"
          size="sm"
          className="h-8 text-xs gap-1.5"
          onClick={onExport}
          disabled={isExporting}
        >
          {isExporting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Download className="h-3.5 w-3.5" />
          )}
          Exportar CSV
        </Button>

        <Button
          data-testid="new-contact-btn"
          size="sm"
          className="h-8 text-xs gap-1.5"
          onClick={onNewContact}
        >
          <Plus className="h-3.5 w-3.5" />
          {newEntityLabel}
        </Button>
      </div>
    </div>
  );
}
