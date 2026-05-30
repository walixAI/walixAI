import { useEffect, useRef } from "react";
import { Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  sending?: boolean;
  sendError?: string | null;
  placeholder?: string;
}

export function Composer({ value, onChange, onSend, sending, sendError, placeholder }: Props) {
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

  return (
    <div className="border-t border-border bg-card">
      {sendError && (
        <div className="px-3 pt-2 text-xs text-red-600 flex items-center gap-1">
          <span className="font-medium">Error:</span> {sendError}
        </div>
      )}
      <div className="p-3 flex items-end gap-2">
        <div className="flex-1">
          <Textarea
            ref={taRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKey}
            placeholder={placeholder ?? "Escribe un mensaje..."}
            rows={1}
            disabled={sending}
            className="resize-none min-h-[36px] max-h-[160px] py-2 w-full"
          />
        </div>
        <Button
          onClick={onSend}
          disabled={!value.trim() || sending}
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
