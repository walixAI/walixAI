import { useState, useEffect, useCallback } from "react";
import { Loader2, Check, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { api, type LeadListItem } from "@/lib/api";
import { useOpportunityStore, oppReadToCard } from "@/stores/opportunityStore";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { toast } from "sonner";

export function NuevaOportunidadModal() {
  const {
    newOppModalOpen,
    newOppStageId,
    closeNewOppModal,
    stages,
    branchId,
    addCardToStage,
  } = useOpportunityStore();

  const defaultStage = stages.find((s) => s.id === newOppStageId) ?? stages[0];
  const defaultProb = defaultStage?.probability_default ?? 50;

  const [form, setForm] = useState({
    title: "",
    amount: "",
    probability: defaultProb,
    stage_id: defaultStage?.id ?? "",
    close_date: "",
    source: "",
    notes: "",
  });
  const [saving, setSaving] = useState(false);

  // Lead combobox state
  const [comboOpen, setComboOpen] = useState(false);
  const [leads, setLeads] = useState<LeadListItem[]>([]);
  const [selectedLead, setSelectedLead] = useState<LeadListItem | null>(null);
  const [leadsLoading, setLeadsLoading] = useState(false);

  // Reset form when modal opens
  useEffect(() => {
    if (newOppModalOpen) {
      const stage = stages.find((s) => s.id === newOppStageId) ?? stages[0];
      setForm({
        title: "",
        amount: "",
        probability: stage?.probability_default ?? 50,
        stage_id: stage?.id ?? "",
        close_date: "",
        source: "",
        notes: "",
      });
      setSelectedLead(null);
    }
  }, [newOppModalOpen, newOppStageId, stages]);

  // Update probability when stage changes
  useEffect(() => {
    const stage = stages.find((s) => s.id === form.stage_id);
    if (stage?.probability_default != null) {
      setForm((f) => ({ ...f, probability: stage.probability_default! }));
    }
  }, [form.stage_id, stages]);

  const fetchLeads = useCallback(async () => {
    setLeadsLoading(true);
    try {
      const res = await api.listLeads({ all: true });
      setLeads(res.items.filter((l) => !(l as unknown as { deleted_at?: string }).deleted_at));
    } catch {
      setLeads([]);
    } finally {
      setLeadsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (comboOpen && leads.length === 0) fetchLeads();
  }, [comboOpen, leads.length, fetchLeads]);

  async function handleCreate() {
    if (!form.title.trim()) {
      toast.error("El título es obligatorio");
      return;
    }
    setSaving(true);
    try {
      const created = await api.createOpportunity({
        title: form.title.trim(),
        amount: form.amount || undefined,
        probability: form.probability,
        stage_id: form.stage_id || undefined,
        lead_id: selectedLead?.id || undefined,
        close_date: form.close_date || undefined,
        source: form.source || undefined,
        notes: form.notes || undefined,
        branch_id: branchId ?? undefined,
      });
      if (form.stage_id) {
        addCardToStage(oppReadToCard(created), form.stage_id);
      }
      closeNewOppModal();
      toast.success("Oportunidad creada");
    } catch (e) {
      toast.error("No se pudo crear la oportunidad", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setSaving(false);
    }
  }

  const [leadSearch, setLeadSearch] = useState("");
  const filteredLeads = leads.filter((l) =>
    (l.name ?? l.wa_phone).toLowerCase().includes(leadSearch.toLowerCase()),
  );

  return (
    <Dialog open={newOppModalOpen} onOpenChange={(o) => { if (!o) closeNewOppModal(); }}>
      <DialogContent className="sm:max-w-[480px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Nueva Oportunidad</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="opp-title" className="text-xs">Título *</Label>
            <Input
              id="opp-title"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="Nombre de la oportunidad"
              className="h-9"
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Contacto (opcional)</Label>
            <Popover open={comboOpen} onOpenChange={setComboOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={comboOpen}
                  aria-label="Seleccionar contacto"
                  className="w-full justify-between h-9 font-normal text-sm"
                >
                  {selectedLead ? (selectedLead.name ?? selectedLead.wa_phone) : "Buscar contacto…"}
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-full p-0" align="start">
                <Command>
                  <CommandInput
                    placeholder="Buscar por nombre o teléfono…"
                    value={leadSearch}
                    onValueChange={setLeadSearch}
                  />
                  <CommandList>
                    {leadsLoading ? (
                      <div className="flex items-center justify-center py-6">
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                      </div>
                    ) : (
                      <>
                        <CommandEmpty>Sin resultados</CommandEmpty>
                        <CommandGroup>
                          {filteredLeads.map((lead) => (
                            <CommandItem
                              key={lead.id}
                              value={lead.id}
                              onSelect={() => {
                                setSelectedLead(lead);
                                setComboOpen(false);
                                setLeadSearch("");
                              }}
                            >
                              <Check
                                className={cn("mr-2 h-4 w-4", selectedLead?.id === lead.id ? "opacity-100" : "opacity-0")}
                                aria-hidden="true"
                              />
                              <span>{lead.name ?? lead.wa_phone}</span>
                              {lead.name && <span className="ml-2 text-xs text-muted-foreground">{lead.wa_phone}</span>}
                            </CommandItem>
                          ))}
                        </CommandGroup>
                      </>
                    )}
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Monto (MXN)</Label>
              <Input
                type="number"
                min={0}
                value={form.amount}
                onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
                placeholder="0"
                className="h-9"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Etapa</Label>
              <select
                value={form.stage_id}
                onChange={(e) => setForm((f) => ({ ...f, stage_id: e.target.value }))}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                aria-label="Etapa de la oportunidad"
              >
                <option value="">Sin etapa</option>
                {stages.filter((s) => !s.is_won && !s.is_lost).map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Probabilidad de cierre: {form.probability}%</Label>
            <Slider
              min={0}
              max={100}
              step={5}
              value={[form.probability]}
              onValueChange={([v]) => setForm((f) => ({ ...f, probability: v }))}
              aria-label="Probabilidad de cierre"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Fecha de cierre</Label>
              <Input
                type="date"
                value={form.close_date}
                onChange={(e) => setForm((f) => ({ ...f, close_date: e.target.value }))}
                className="h-9"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Fuente</Label>
              <select
                value={form.source}
                onChange={(e) => setForm((f) => ({ ...f, source: e.target.value }))}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                aria-label="Fuente de captación"
              >
                <option value="">Sin especificar</option>
                <option value="whatsapp">WhatsApp</option>
                <option value="web_form">Formulario web</option>
                <option value="referral">Referido</option>
                <option value="manual">Manual</option>
              </select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Notas (opcional)</Label>
            <Textarea
              rows={2}
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              placeholder="Notas internas…"
              className="resize-none"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={closeNewOppModal} disabled={saving}>Cancelar</Button>
          <Button onClick={handleCreate} disabled={saving || !form.title.trim()} className="gap-1.5">
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            Crear Oportunidad
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
