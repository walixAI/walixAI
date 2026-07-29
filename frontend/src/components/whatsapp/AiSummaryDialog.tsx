import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, FileText, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { createActivity } from "@/lib/queries/activities";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  conversationId: string;
  contactId: string;
}

export function AiSummaryDialog({ open, onOpenChange, conversationId, contactId }: Props) {
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["conversation-summary", conversationId],
    queryFn: () => api.getConversationSummary(conversationId),
    enabled: open && !!conversationId,
    staleTime: 5 * 60_000,
  });

  const summary = data?.summary ?? "";

  const handleCopy = () => {
    navigator.clipboard.writeText(summary);
    toast.success("Resumen copiado");
  };

  const handleSaveNote = async () => {
    await createActivity(contactId, {
      activityType: "note",
      title: "Resumen de conversación (IA)",
      body: summary,
    });
    await qc.invalidateQueries({ queryKey: ["activities", contactId] });
    toast.success("Guardado como nota");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-purple-500" />
            Resumen de conversación
          </DialogTitle>
        </DialogHeader>

        <div className="min-h-[100px]">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          )}
          {isError && (
            <p className="text-sm text-destructive">
              No se pudo generar el resumen. Intenta de nuevo.
            </p>
          )}
          {!isLoading && !isError && summary && (
            <p className="text-sm text-muted-foreground leading-relaxed">{summary}</p>
          )}
        </div>

        <DialogFooter className="gap-2 sm:justify-between">
          <Button variant="outline" size="sm" onClick={handleCopy} disabled={!summary}>
            <Copy className="mr-2 h-3.5 w-3.5" />
            Copiar
          </Button>
          <Button size="sm" onClick={handleSaveNote} disabled={!summary}>
            <FileText className="mr-2 h-3.5 w-3.5" />
            Guardar como nota
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
