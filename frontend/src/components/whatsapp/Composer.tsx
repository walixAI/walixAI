import { useEffect, useRef } from "react";
import { Send, Loader2, Sparkles, X, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
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
}: Props) {
  const windowClosed = serviceWindow !== undefined && !serviceWindow.open;
  const taRef = useRef<HTMLTextAreaElement>(null);

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
