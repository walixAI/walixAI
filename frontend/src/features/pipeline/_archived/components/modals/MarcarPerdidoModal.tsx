import { useState } from "react";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useOpportunityStore } from "@/stores/opportunityStore";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

const REASON_CODES = [
  { value: "price", label: "Precio" },
  { value: "competitor", label: "Competencia" },
  { value: "no_budget", label: "Sin presupuesto" },
  { value: "no_response", label: "Sin respuesta" },
  { value: "other", label: "Otro" },
];

export function MarcarPerdidoModal() {
  const { lostModalOppId, closeLostModal, refreshBoardCard } = useOpportunityStore();
  const [form, setForm] = useState({ lost_reason: "", reason_code: "other" });
  const [saving, setSaving] = useState(false);

  const isOpen = !!lostModalOppId;

  async function handleSubmit() {
    if (!lostModalOppId) return;
    if (!form.lost_reason.trim()) {
      toast.error("El motivo es obligatorio");
      return;
    }
    setSaving(true);
    try {
      const updated = await api.markOpportunityLost(lostModalOppId, {
        lost_reason: form.lost_reason.trim(),
        reason_code: form.reason_code,
      });
      refreshBoardCard(updated);
      closeLostModal();
      setForm({ lost_reason: "", reason_code: "other" });
      toast.success("Oportunidad marcada como perdida");
    } catch (e) {
      toast.error("No se pudo marcar como perdida", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(o) => { if (!o) { closeLostModal(); setForm({ lost_reason: "", reason_code: "other" }); } }}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Marcar como Perdida</DialogTitle>
          <DialogDescription>
            Indica el motivo de pérdida para registrar el aprendizaje.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label className="text-xs">Razón de pérdida *</Label>
            <select
              value={form.reason_code}
              onChange={(e) => setForm((f) => ({ ...f, reason_code: e.target.value }))}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              aria-label="Razón de pérdida"
            >
              {REASON_CODES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Describe el motivo *</Label>
            <Textarea
              rows={3}
              value={form.lost_reason}
              onChange={(e) => setForm((f) => ({ ...f, lost_reason: e.target.value }))}
              placeholder="¿Por qué se perdió esta oportunidad?"
              autoFocus
              className="resize-none"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => { closeLostModal(); setForm({ lost_reason: "", reason_code: "other" }); }} disabled={saving}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            onClick={handleSubmit}
            disabled={saving || !form.lost_reason.trim()}
            className="gap-1.5"
          >
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            Marcar Perdida
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
