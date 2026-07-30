import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageCircle, Phone, MoreHorizontal } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { updateActivity, type ClosedVia } from "@/lib/queries/activities";
import { useCloseTask } from "@/lib/queries/tasks";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface CloseTaskRef {
  id: string;
  title: string | null;
  taskKind: string | null;
  dueDate: string | null;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contactId: string;
  task: CloseTaskRef;
  leadName?: string | null;
}

type Mode = "resolver" | "reagendar";
type Method = "whatsapp" | "call" | "other";
type CallResult = "answered" | "no_answer" | "voicemail";

// ── Helpers ───────────────────────────────────────────────────────────────────

function suggestMethod(taskKind: string | null): Method {
  if (taskKind === "cobro" || taskKind === "seguimiento") return "whatsapp";
  if (taskKind === "servicio" || taskKind === "queja") return "call";
  return "other";
}

function draftMessage(leadName: string | null | undefined, task: CloseTaskRef): string {
  return `Hola ${leadName ?? ""}, te escribo por: ${task.title ?? task.taskKind ?? "tu tarea"}`;
}

function toLocalInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

const QUICK_DATES = () => {
  const now = new Date();
  const in2h = new Date(now.getTime() + 2 * 3600 * 1000);
  const tmrw = new Date(now); tmrw.setDate(tmrw.getDate() + 1); tmrw.setHours(9, 0, 0, 0);
  const in3d = new Date(now); in3d.setDate(in3d.getDate() + 3); in3d.setHours(9, 0, 0, 0);
  return [
    { label: "En 2h",       value: toLocalInput(in2h) },
    { label: "Mañana 9am",  value: toLocalInput(tmrw) },
    { label: "En 3 días",   value: toLocalInput(in3d) },
  ];
};

const METHODS: { id: Method; label: string; icon: React.ElementType }[] = [
  { id: "whatsapp", label: "WhatsApp", icon: MessageCircle },
  { id: "call",     label: "Llamada",  icon: Phone },
  { id: "other",    label: "Otro",     icon: MoreHorizontal },
];

// ── Component ─────────────────────────────────────────────────────────────────

export function CloseTaskDialog({ open, onOpenChange, contactId, task, leadName }: Props) {
  const qc = useQueryClient();
  const closeTask = useCloseTask();

  const [mode, setMode] = useState<Mode>("resolver");
  const [method, setMethod] = useState<Method>("whatsapp");
  const [waMessage, setWaMessage] = useState("");
  const [callResult, setCallResult] = useState<CallResult | null>(null);
  const [callNote, setCallNote] = useState("");
  const [otherNote, setOtherNote] = useState("");
  const [newDueDate, setNewDueDate] = useState("");
  const [motivo, setMotivo] = useState("");

  // Reset state each time the dialog opens (possibly for a new task)
  useEffect(() => {
    if (!open) return;
    setMode("resolver");
    setMethod(suggestMethod(task.taskKind));
    setWaMessage(draftMessage(leadName, task));
    setCallResult(null);
    setCallNote("");
    setOtherNote("");
    setNewDueDate("");
    setMotivo("");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, task.id]);

  // WhatsApp: send then close task
  const waMutation = useMutation({
    mutationFn: async () => {
      await api.reply(contactId, waMessage);
      await updateActivity(contactId, task.id, {
        completedAt: new Date().toISOString(),
        closedVia: "whatsapp",
        closedNote: waMessage.slice(0, 160),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks-today"] });
      qc.invalidateQueries({ queryKey: ["activities", contactId] });
      toast.success("Mensaje enviado y tarea cerrada");
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message ?? "Error al enviar"),
  });

  // Reschedule: update due_date only, completed_at untouched
  const rescheduleMutation = useMutation({
    mutationFn: () =>
      updateActivity(contactId, task.id, { dueDate: new Date(newDueDate).toISOString() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks-today"] });
      qc.invalidateQueries({ queryKey: ["activities", contactId] });
      toast.success("Tarea reagendada");
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message ?? "Error al reagendar"),
  });

  function closeWith(closedVia: ClosedVia, note: string) {
    closeTask.mutate(
      { leadId: contactId, activityId: task.id, closedVia, closedNote: note, contactId },
      {
        onSuccess: () => { toast.success("Tarea cerrada"); onOpenChange(false); },
        onError: (e) => toast.error((e as Error).message ?? "Error"),
      },
    );
  }

  function onCallResultChange(val: string) {
    const r = val as CallResult;
    setCallResult(r);
    if (r === "no_answer" || r === "voicemail") {
      setMotivo("No contestó — reintentar");
      setMode("reagendar");
    }
  }

  const busy = waMutation.isPending || rescheduleMutation.isPending || closeTask.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base leading-snug line-clamp-2">
            {task.title ?? task.taskKind ?? "Tarea"}
          </DialogTitle>
        </DialogHeader>

        {/* Mode toggle */}
        <div className="flex rounded-lg border border-border bg-muted p-1 gap-1">
          {(["resolver", "reagendar"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={cn(
                "flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                mode === m
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {m === "resolver" ? "Resolver" : "Reagendar"}
            </button>
          ))}
        </div>

        {/* ─── RESOLVER ─────────────────────────────────────────────────── */}
        {mode === "resolver" && (
          <div className="space-y-4">
            {/* Method tiles */}
            <div className="grid grid-cols-3 gap-2">
              {METHODS.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setMethod(id)}
                  className={cn(
                    "flex flex-col items-center gap-1.5 rounded-xl border py-3 text-xs font-medium transition-colors",
                    method === id
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>

            {/* WhatsApp content */}
            {method === "whatsapp" && (
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Mensaje a enviar</Label>
                <Textarea
                  rows={3}
                  value={waMessage}
                  onChange={(e) => setWaMessage(e.target.value)}
                  className="resize-none text-sm"
                />
                <Button
                  className="w-full"
                  disabled={busy || !waMessage.trim()}
                  onClick={() => waMutation.mutate()}
                >
                  {waMutation.isPending ? "Enviando…" : "Enviar y cerrar"}
                </Button>
              </div>
            )}

            {/* Llamada content */}
            {method === "call" && (
              <div className="space-y-3">
                <Label className="text-xs text-muted-foreground">Resultado de la llamada</Label>
                <RadioGroup
                  value={callResult ?? ""}
                  onValueChange={onCallResultChange}
                  className="gap-2"
                >
                  {[
                    { val: "answered",  label: "Contestó" },
                    { val: "no_answer", label: "No contestó" },
                    { val: "voicemail", label: "Buzón" },
                  ].map(({ val, label }) => (
                    <div key={val} className="flex items-center gap-2">
                      <RadioGroupItem value={val} id={`call-${val}`} />
                      <Label htmlFor={`call-${val}`} className="cursor-pointer text-sm font-normal">
                        {label}
                      </Label>
                    </div>
                  ))}
                </RadioGroup>

                {callResult === "answered" && (
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Nota breve (requerida)</Label>
                    <Textarea
                      rows={2}
                      placeholder="¿Qué se acordó?"
                      value={callNote}
                      onChange={(e) => setCallNote(e.target.value)}
                      className="resize-none text-sm"
                    />
                    <Button
                      className="w-full"
                      disabled={busy || !callNote.trim()}
                      onClick={() => closeWith("call", callNote)}
                    >
                      {closeTask.isPending ? "Cerrando…" : "Cerrar tarea"}
                    </Button>
                  </div>
                )}
              </div>
            )}

            {/* Otro content */}
            {method === "other" && (
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Nota (requerida)</Label>
                <Textarea
                  rows={3}
                  placeholder="¿Cómo se resolvió?"
                  value={otherNote}
                  onChange={(e) => setOtherNote(e.target.value)}
                  className="resize-none text-sm"
                />
                <Button
                  className="w-full"
                  disabled={busy || !otherNote.trim()}
                  onClick={() => closeWith("other", otherNote)}
                >
                  {closeTask.isPending ? "Cerrando…" : "Cerrar tarea"}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* ─── REAGENDAR ────────────────────────────────────────────────── */}
        {mode === "reagendar" && (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Nueva fecha y hora</Label>
              <Input
                type="datetime-local"
                value={newDueDate}
                onChange={(e) => setNewDueDate(e.target.value)}
                className="text-sm"
              />
            </div>

            <div className="flex gap-2">
              {QUICK_DATES().map(({ label, value }) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => setNewDueDate(value)}
                  className={cn(
                    "flex-1 rounded-lg border px-2 py-2 text-xs font-medium transition-colors",
                    newDueDate === value
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Motivo (opcional)</Label>
              <Textarea
                rows={2}
                placeholder="¿Por qué se reagenda?"
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                className="resize-none text-sm"
              />
            </div>

            <Button
              className="w-full"
              disabled={busy || !newDueDate}
              onClick={() => rescheduleMutation.mutate()}
            >
              {rescheduleMutation.isPending ? "Reagendando…" : "Reagendar"}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
