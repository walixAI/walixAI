import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { createActivity, updateActivity } from "@/lib/queries/activities";
import { useContactsLite } from "@/lib/queries/pipeline";
import type { TaskRow } from "@/lib/queries/tasks";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contactId?: string;       // predefined (skip contact search when set)
  contactName?: string;     // displayed label when predefined
  task?: TaskRow;           // edit mode when present
}

const TASK_KIND_OPTIONS = [
  { value: "cobro",        label: "Cobro" },
  { value: "cotizacion",   label: "Cotización" },
  { value: "servicio",     label: "Servicio" },
  { value: "seguimiento",  label: "Seguimiento" },
  { value: "queja",        label: "Queja" },
  { value: "refaccion",    label: "Refacción" },
  { value: "facturacion",  label: "Facturación" },
  { value: "devolucion",   label: "Devolución" },
  { value: "otro",         label: "Otro" },
] as const;

function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function QuickTaskDialog({
  open,
  onOpenChange,
  contactId: predefinedContactId,
  contactName: predefinedContactName,
  task,
}: Props) {
  const qc = useQueryClient();
  const isEdit = !!task;

  const [title, setTitle] = useState("");
  const [taskKind, setTaskKind] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [contactSearch, setContactSearch] = useState("");
  const [saving, setSaving] = useState(false);

  const { data: contacts = [] } = useContactsLite();

  useEffect(() => {
    if (!open) return;
    setTitle(task?.title ?? "");
    setTaskKind(task?.taskKind ?? "");
    setDueDate(toLocalInput(task?.dueDate));
    setSelectedContactId(predefinedContactId ?? task?.leadId ?? null);
    setContactSearch("");
    setSaving(false);
  }, [open, task?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const effectiveContactId = predefinedContactId ?? selectedContactId;

  const filteredContacts = contactSearch
    ? contacts.filter((c) =>
        `${c.name} ${c.lastName ?? ""}`.toLowerCase().includes(contactSearch.toLowerCase()),
      )
    : contacts.slice(0, 30);

  const selectedContact = contacts.find((c) => c.id === effectiveContactId);
  const displayContactName =
    predefinedContactName ??
    (selectedContact ? `${selectedContact.name} ${selectedContact.lastName ?? ""}`.trim() : null);

  async function onSubmit() {
    if (!title.trim()) { toast.error("El título es obligatorio"); return; }
    if (!effectiveContactId) { toast.error("Selecciona un contacto"); return; }

    setSaving(true);
    try {
      const dueDateIso = dueDate ? new Date(dueDate).toISOString() : null;
      if (isEdit && task) {
        await updateActivity(task.leadId, task.id, {
          title: title.trim(),
          taskKind: taskKind || null,
          dueDate: dueDateIso,
        });
        toast.success("Tarea actualizada");
      } else {
        await createActivity(effectiveContactId, {
          activityType: "task",
          title: title.trim(),
          taskKind: taskKind || null,
          dueDate: dueDateIso,
        });
        toast.success("Tarea creada");
      }
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["tasks-today"] });
      if (effectiveContactId) {
        qc.invalidateQueries({ queryKey: ["activities", effectiveContactId] });
      }
      onOpenChange(false);
    } catch (e: unknown) {
      toast.error((e as Error)?.message ?? "Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Editar tarea" : "Nueva tarea"}</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          {/* Title */}
          <div className="space-y-1.5">
            <Label>Título *</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="¿Qué hay que hacer?"
              autoFocus
            />
          </div>

          {/* Task kind */}
          <div className="space-y-1.5">
            <Label>Tipo de tarea</Label>
            <Select value={taskKind} onValueChange={setTaskKind}>
              <SelectTrigger>
                <SelectValue placeholder="Selecciona un tipo…" />
              </SelectTrigger>
              <SelectContent>
                {TASK_KIND_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Due date */}
          <div className="space-y-1.5">
            <Label>Fecha y hora límite</Label>
            <Input
              type="datetime-local"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="text-sm"
            />
          </div>

          {/* Contact — show search only when not predefined */}
          <div className="space-y-1.5">
            <Label>Contacto *</Label>
            {predefinedContactId ? (
              <Input value={displayContactName ?? predefinedContactId} disabled className="text-sm" />
            ) : (
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" className={cn("w-full justify-start font-normal", !effectiveContactId && "text-muted-foreground")}>
                    {displayContactName ?? "Buscar contacto…"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="p-0 w-[var(--radix-popover-trigger-width)]" align="start">
                  <Command shouldFilter={false}>
                    <CommandInput
                      placeholder="Buscar…"
                      value={contactSearch}
                      onValueChange={setContactSearch}
                    />
                    <CommandList>
                      <CommandEmpty>Sin resultados</CommandEmpty>
                      <CommandGroup>
                        {filteredContacts.map((c) => (
                          <CommandItem
                            key={c.id}
                            value={c.id}
                            onSelect={() => setSelectedContactId(c.id)}
                          >
                            {c.name} {c.lastName ?? ""}
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button onClick={onSubmit} disabled={saving}>
            {saving ? "Guardando…" : isEdit ? "Guardar" : "Crear"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
