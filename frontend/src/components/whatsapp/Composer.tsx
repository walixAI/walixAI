import { useEffect, useRef, useState } from "react";
import { Send, Loader2, Sparkles, X, Lock, FileText } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { ServiceWindow } from "@/lib/whatsapp/serviceWindow";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  sending?: boolean;
  sendError?: string | null;
  placeholder?: string;
  onAiSuggest?: () => void;
  aiLoading?: boolean;
  aiDraftActive?: boolean;
  onClearAiDraft?: () => void;
  serviceWindow?: ServiceWindow;
  /** Required for the template selector (when window is closed) */
  leadId?: string;
  branchId?: string;
}

export function Composer({
  value,
  onChange,
  onSend,
  sending,
  sendError,
  placeholder,
  onAiSuggest,
  aiLoading,
  aiDraftActive,
  onClearAiDraft,
  serviceWindow,
  leadId,
  branchId,
}: Props) {
  const windowClosed = serviceWindow !== undefined && !serviceWindow.open;
  const taRef = useRef<HTMLTextAreaElement>(null);
  const qc = useQueryClient();

  const [selectedTemplateId, setSelectedTemplateId] = useState<string>("");

  // auto-grow
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  // Focus after send completes
  useEffect(() => {
    if (!sending) taRef.current?.focus();
  }, [sending]);

  // Reset template selection when lead changes
  useEffect(() => {
    setSelectedTemplateId("");
  }, [leadId]);

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !sending) onSend();
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    if (aiDraftActive) onClearAiDraft?.();
    onChange(e.target.value);
  };

  // Fetch templates only when window is closed and we have a branch
  const { data: templates = [] } = useQuery({
    queryKey: ["branch-templates", branchId],
    queryFn: () => api.listBranchTemplates(branchId!),
    enabled: windowClosed && !!branchId,
    staleTime: 60_000,
  });

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId) ?? null;

  // Group templates by category for the dropdown
  const byCategory = templates.reduce<Record<string, typeof templates>>((acc, t) => {
    (acc[t.category] ??= []).push(t);
    return acc;
  }, {});

  const sendTemplateMutation = useMutation({
    mutationFn: () => api.sendTemplate(leadId!, selectedTemplateId),
    onSuccess: () => {
      setSelectedTemplateId("");
      qc.invalidateQueries({ queryKey: ["conversation", leadId] });
      toast.success("Plantilla enviada");
    },
    onError: (e: Error) => toast.error("Error al enviar plantilla", { description: e.message }),
  });

  const canSendTemplate = !!leadId && !!selectedTemplateId && !sendTemplateMutation.isPending;

  return (
    <div className="border-t border-border bg-card">
      {/* Ventana cerrada — banner */}
      {windowClosed && (
        <div className="px-3 pt-3 pb-1">
          <div className="flex items-start gap-2 rounded-lg bg-danger/5 border border-danger/20 px-3 py-2 text-danger">
            <Lock className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <p className="text-xs leading-snug">
              <span className="font-semibold">Ventana de 24 h cerrada.</span>{" "}
              {serviceWindow!.description}
            </p>
          </div>
        </div>
      )}

      {/* Template selector — only shown when window is closed */}
      {windowClosed && (
        <div className="px-3 pt-2 pb-1 space-y-2">
          <p className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            Enviar plantilla aprobada de WhatsApp
          </p>

          {templates.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No hay plantillas activas para esta sucursal.
            </p>
          ) : (
            <div className="flex items-start gap-2">
              <div className="flex-1 space-y-1.5">
                <Select
                  value={selectedTemplateId}
                  onValueChange={setSelectedTemplateId}
                  disabled={sendTemplateMutation.isPending}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Selecciona una plantilla…" />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(byCategory).map(([cat, items]) => (
                      <SelectGroup key={cat}>
                        <SelectLabel className="text-xs">{cat}</SelectLabel>
                        {items.map((t) => (
                          <SelectItem key={t.id} value={t.id} className="text-xs">
                            {t.name}
                            {t.branch_id === null && (
                              <span className="ml-1.5 text-[9px] font-semibold uppercase bg-primary/10 text-primary px-1 py-0.5 rounded">
                                Global
                              </span>
                            )}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    ))}
                  </SelectContent>
                </Select>

                {selectedTemplate?.body_preview && (
                  <p className="text-[11px] text-muted-foreground leading-snug line-clamp-3 border border-border rounded px-2 py-1.5 bg-muted/40">
                    {selectedTemplate.body_preview}
                  </p>
                )}
              </div>

              <Button
                size="sm"
                className="h-8 px-3 text-xs shrink-0"
                disabled={!canSendTemplate}
                onClick={() => sendTemplateMutation.mutate()}
              >
                {sendTemplateMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Send className="h-3.5 w-3.5" />
                )}
                <span className="ml-1.5">Enviar</span>
              </Button>
            </div>
          )}
        </div>
      )}

      {/* AI suggest row */}
      <div className="px-3 pt-2 flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={onAiSuggest}
          disabled={aiLoading || sending}
          className="h-7 px-2 text-xs text-primary gap-1.5 hover:bg-primary/10"
        >
          {aiLoading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="h-3.5 w-3.5" />
          )}
          Sugerir respuesta
        </Button>
      </div>

      {/* AI draft badge */}
      {aiDraftActive && (
        <div className="px-3 pt-1 flex items-center gap-1.5">
          <span className="inline-flex items-center gap-1 text-xs bg-primary/5 border border-primary/40 text-primary rounded-full px-2 py-0.5">
            <Sparkles className="h-3 w-3" />
            Borrador IA
          </span>
          <button
            onClick={onClearAiDraft}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Descartar borrador"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {sendError && (
        <div className="px-3 pt-2 text-xs text-danger flex items-center gap-1">
          <span className="font-medium">Error:</span> {sendError}
        </div>
      )}
      <div className="p-3 flex items-end gap-2">
        <div className="flex-1">
          <Textarea
            ref={taRef}
            value={value}
            onChange={handleChange}
            onKeyDown={onKey}
            placeholder={
              windowClosed
                ? "Ventana cerrada · no puedes enviar texto libre"
                : (placeholder ?? "Escribe un mensaje...")
            }
            rows={1}
            disabled={sending || windowClosed}
            className="resize-none min-h-[36px] max-h-[160px] py-2 w-full"
          />
        </div>
        <Button
          onClick={onSend}
          disabled={!value.trim() || sending || windowClosed}
          size="icon"
          className="h-9 w-9 shrink-0"
        >
          {sending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  );
}
