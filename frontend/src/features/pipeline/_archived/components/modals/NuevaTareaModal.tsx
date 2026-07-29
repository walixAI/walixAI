import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { api, type TeamMemberOut } from "@/lib/api";
import { useOpportunityStore } from "../../opportunityStore";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

export function NuevaTareaModal() {
  const { taskModalOppId, closeTaskModal, branchId } = useOpportunityStore();
  const [form, setForm] = useState({ title: "", due_date: "", assigned_to: "" });
  const [saving, setSaving] = useState(false);
  const [team, setTeam] = useState<TeamMemberOut[]>([]);

  const isOpen = !!taskModalOppId;

  useEffect(() => {
    if (isOpen) {
      api.getTeam(branchId ?? "").then(setTeam).catch(() => {});
      setForm({ title: "", due_date: "", assigned_to: "" });
    }
  }, [isOpen, branchId]);

  async function handleCreate() {
    if (!form.title.trim()) {
      toast.error("El título de la tarea es obligatorio");
      return;
    }
    setSaving(true);
    try {
      // Stub: API endpoint for opportunity tasks is pending (Prompt 5+)
      await new Promise((resolve) => setTimeout(resolve, 400));
      closeTaskModal();
      toast.success("Tarea creada (simulado — API pendiente)");
    } catch (e) {
      toast.error("Error al crear tarea", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(o) => { if (!o) closeTaskModal(); }}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Nueva Tarea</DialogTitle>
          <DialogDescription>
            Vincula una tarea de seguimiento a esta oportunidad.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="task-title" className="text-xs">Título *</Label>
            <Input
              id="task-title"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="ej. Enviar propuesta comercial"
              className="h-9"
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Vencimiento</Label>
            <Input
              type="date"
              value={form.due_date}
              onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))}
              className="h-9"
            />
          </div>

          {team.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-xs">Asignar a</Label>
              <select
                value={form.assigned_to}
                onChange={(e) => setForm((f) => ({ ...f, assigned_to: e.target.value }))}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                aria-label="Asignar tarea a"
              >
                <option value="">Sin asignar</option>
                {team.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={closeTaskModal} disabled={saving}>Cancelar</Button>
          <Button onClick={handleCreate} disabled={saving || !form.title.trim()} className="gap-1.5">
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
            Crear Tarea
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
