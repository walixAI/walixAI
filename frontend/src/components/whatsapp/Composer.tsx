import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  onSend: (text: string) => void;
  sending?: boolean;
}

export function Composer({ onSend, sending }: Props) {
  const [draft, setDraft] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  // auto-grow
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [draft]);

  const submit = () => {
    const v = draft.trim();
    if (!v) return;
    onSend(v);
    setDraft("");
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-border bg-card p-3 flex items-end gap-2">
      <div className="flex-1">
        <Textarea
          ref={taRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          placeholder="Escribe un mensaje..."
          rows={1}
          className="resize-none min-h-[36px] max-h-[160px] py-2 w-full"
        />
      </div>
      <Button onClick={submit} disabled={!draft.trim() || sending} size="icon" className="h-9 w-9 shrink-0">
        <Send className="h-4 w-4" />
      </Button>
    </div>
  );
}
