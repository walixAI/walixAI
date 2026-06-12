import { useState } from "react";
import { useForm } from "react-hook-form";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { ActivityType, ActivityCreate } from "@/lib/queries/activities";

const ACTIVITY_TYPES: { value: ActivityType; label: string; emoji: string }[] = [
  { value: "note",    label: "Nota",     emoji: "📝" },
  { value: "task",    label: "Tarea",    emoji: "✅" },
  { value: "call",    label: "Llamada",  emoji: "📞" },
  { value: "meeting", label: "Reunión",  emoji: "📅" },
  { value: "email",   label: "Email",    emoji: "✉️" },
];

const OUTCOMES = [
  { value: "answered",  label: "Contestó" },
  { value: "no_answer", label: "No contestó" },
  { value: "voicemail", label: "Buzón de voz" },
];

function getTomorrowDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().split("T")[0];
}

interface FormData {
  title: string;
  body: string;
  due_date: string;
  duration_minutes: string;
  outcome: string;
}

interface ActivityFormDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSubmit: (data: ActivityCreate) => Promise<void>;
}

export function ActivityFormDialog({ open, onOpenChange, onSubmit }: ActivityFormDialogProps) {
  const [actType, setActType] = useState<ActivityType>("note");
  const { register, handleSubmit, reset, setValue, watch, formState: { errors, isSubmitting } } = useForm<FormData>({
    defaultValues: { title: "", body: "", due_date: getTomorrowDate(), duration_minutes: "", outcome: "" },
  });

  const handleClose = () => {
    reset();
    setActType("note");
    onOpenChange(false);
  };

  const doSubmit = handleSubmit(async (d) => {
    const metadata: Record<string, unknown> = {};
    if (d.duration_minutes) metadata.duration_minutes = Number(d.duration_minutes);
    if (d.outcome) metadata.outcome = d.outcome;

    await onSubmit({
      activityType: actType,
      title: d.title || null,
      body: d.body || null,
      dueDate: (actType === "task" || actType === "meeting") ? d.due_date || null : null,
      metadata: Object.keys(metadata).length > 0 ? metadata : null,
    });
    handleClose();
  });

  const needsTitle = actType !== "note";
  const needsDueDate = actType === "task" || actType === "meeting";
  const needsDuration = actType === "call" || actType === "meeting";
  const needsOutcome = actType === "call";

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose(); }}>
      <DialogContent data-testid="activity-form-dialog" className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Registrar actividad</DialogTitle>
        </DialogHeader>

        {/* Type selector */}
        <div className="flex gap-1.5 flex-wrap">
          {ACTIVITY_TYPES.map(({ value, label, emoji }) => (
            <button
              key={value}
              type="button"
              data-testid={`type-${value}`}
              onClick={() => setActType(value)}
              className={cn(
                "flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors",
                actType === value
                  ? "bg-primary text-primary-foreground border-primary"
                  : "border-border hover:bg-muted",
              )}
            >
              <span>{emoji}</span>
              {label}
            </button>
          ))}
        </div>

        <form onSubmit={doSubmit} className="space-y-3 mt-1">
          {/* Title */}
          {needsTitle && (
            <div className="space-y-1">
              <Label>{actType === "email" ? "Asunto *" : "Título *"}</Label>
              <Input
                {...register("title", { required: needsTitle ? "Requerido" : false })}
                placeholder={actType === "call" ? "Ej: Seguimiento propuesta" : actType === "meeting" ? "Ej: Demo del producto" : ""}
                className={errors.title ? "border-destructive" : ""}
              />
              {errors.title && <p className="text-xs text-destructive">{errors.title.message}</p>}
            </div>
          )}

          {/* Body */}
          <div className="space-y-1">
            <Label>{actType === "note" ? "Nota *" : "Descripción"}</Label>
            <Textarea
              data-testid="activity-body"
              {...register("body", { required: actType === "note" ? "Escribe una nota" : false })}
              rows={3}
              placeholder={actType === "note" ? "Escribe tu nota…" : "Notas adicionales (opcional)…"}
              className={errors.body ? "border-destructive" : ""}
            />
            {errors.body && <p className="text-xs text-destructive">{errors.body.message}</p>}
          </div>

          {/* Due date */}
          {needsDueDate && (
            <div className="space-y-1">
              <Label>{actType === "task" ? "Fecha límite" : "Fecha de reunión"}</Label>
              <Input type="date" {...register("due_date")} className="h-8 text-sm" />
            </div>
          )}

          {/* Duration */}
          {needsDuration && (
            <div className="space-y-1">
              <Label>Duración (minutos)</Label>
              <Input
                type="number"
                min="1"
                max="480"
                {...register("duration_minutes")}
                placeholder="30"
                className="h-8 text-sm"
              />
            </div>
          )}

          {/* Outcome */}
          {needsOutcome && (
            <div className="space-y-1">
              <Label>Resultado</Label>
              <Select value={watch("outcome")} onValueChange={(v) => setValue("outcome", v)}>
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue placeholder="Seleccionar…" />
                </SelectTrigger>
                <SelectContent>
                  {OUTCOMES.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={handleClose}>Cancelar</Button>
            <Button data-testid="save-activity-btn" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Guardando…" : "Registrar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
