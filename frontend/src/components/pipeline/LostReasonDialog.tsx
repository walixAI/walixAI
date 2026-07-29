import { useEffect, useState } from "react";
import { z } from "zod";
import { useTenantLabels } from "@/hooks/useTenantLabels";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useUpdateDeal, type PipelineDeal, type PipelineStage } from "@/lib/queries/pipeline";

export const LOST_REASONS = [
  { value: "price", label: "Precio" },
  { value: "timing", label: "Timing" },
  { value: "competition", label: "Competencia" },
  { value: "no_response", label: "No responde" },
  { value: "other", label: "Otro" },
] as const;

const schema = z.object({
  reason: z.enum(["price", "timing", "competition", "no_response", "other"]),
  comment: z.string().trim().max(500, "Máximo 500 caracteres").optional(),
});

interface Props {
  open: boolean;
  deal: PipelineDeal | null;
  lostStage: PipelineStage | null;
  onClose: (confirmed: boolean) => void;
}

export function LostReasonDialog({ open, deal, lostStage, onClose }: Props) {
  const { deal: dealLabel } = useTenantLabels();
  const [reason, setReason] = useState<string>("price");
  const [comment, setComment] = useState("");
  const update = useUpdateDeal();

  useEffect(() => {
    if (open) {
      setReason("price");
      setComment("");
    }
  }, [open]);

  async function confirm() {
    if (!deal || !lostStage) return;
    const parsed = schema.safeParse({ reason, comment: comment || undefined });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? "Datos inválidos");
      return;
    }
    try {
      await update.mutateAsync({
        dealId: deal.id,
        patch: {
          pipeline_stage_id: lostStage.id, // Walix: pipeline_stage_id (no stage_id/stage_name)
          is_won: false,
          is_lost: true,
          lost_reason: parsed.data.reason,
          lost_comment: parsed.data.comment ?? null,
        },
      });
      toast.success(`${dealLabel} marcada como perdida`);
      onClose(true);
    } catch (e: any) {
      toast.error(e?.message ?? "No se pudo guardar");
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>¿Por qué se pierde esta {dealLabel.toLowerCase()}?</DialogTitle>
          <DialogDescription>
            Esta información nos ayuda a mejorar el pipeline y entender patrones de pérdida.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label className="text-sm font-medium">Motivo principal</Label>
            <RadioGroup value={reason} onValueChange={setReason} className="grid grid-cols-2 gap-2">
              {LOST_REASONS.map((r) => (
                <label
                  key={r.value}
                  htmlFor={`lr-${r.value}`}
                  className="flex items-center gap-2 rounded-md border border-border px-3 py-2 cursor-pointer hover:bg-muted/50 has-[:checked]:bg-primary/5 has-[:checked]:border-primary"
                >
                  <RadioGroupItem value={r.value} id={`lr-${r.value}`} />
                  <span className="text-sm">{r.label}</span>
                </label>
              ))}
            </RadioGroup>
          </div>

          <div className="space-y-2">
            <Label className="text-sm font-medium">Comentario (opcional)</Label>
            <Textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Detalles adicionales…"
              rows={3}
              maxLength={500}
            />
            <p className="text-xs text-muted-foreground text-right">{comment.length}/500</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)}>Cancelar</Button>
          <Button onClick={confirm} disabled={update.isPending} className="bg-danger hover:bg-danger/90 text-danger-foreground">
            {update.isPending ? "Guardando…" : "Marcar como perdida"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
