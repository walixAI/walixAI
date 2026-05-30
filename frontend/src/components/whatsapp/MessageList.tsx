import { useEffect, useRef } from "react";
import { Loader2, AlertCircle, CheckCheck } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { MessageOut } from "@/lib/api";
import { MessageListSkeleton } from "@/components/walix/Skeletons";

export type PendingMsg = MessageOut & {
  _status: "sending" | "error";
  _errorText?: string;
};

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
}

function dateLabel(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  const yest = new Date();
  yest.setDate(today.getDate() - 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(d, today)) return "Hoy";
  if (same(d, yest)) return "Ayer";
  return d.toLocaleDateString("es-MX", { day: "2-digit", month: "long", year: "numeric" });
}

function AssistantBadge({ isHuman }: { isHuman: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full mb-1",
        isHuman
          ? "bg-blue-100 text-blue-700"
          : "bg-emerald-100 text-emerald-700"
      )}
    >
      {isHuman ? "👤 Asistente" : "🤖 Wali"}
    </span>
  );
}

function MessageBubble({ m }: { m: MessageOut | PendingMsg }) {
  const pending = m as PendingMsg;
  const isPending = "_status" in m;
  const isSending = isPending && pending._status === "sending";
  const isError = isPending && pending._status === "error";

  const isUser = m.role === "user";
  const isSystem = m.role === "system";
  const isHumanAssistant = m.role === "assistant" && !!m.sent_by_user_id;
  const isBotAssistant = m.role === "assistant" && !m.sent_by_user_id;

  if (isSystem) {
    return (
      <div className="flex justify-center">
        <div className="max-w-[75%] bg-muted border border-border rounded-lg px-3 py-2 text-xs text-muted-foreground text-center">
          {m.content}
          <div className="text-[10px] mt-1">{formatTime(m.created_at)}</div>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col", isUser ? "items-start" : "items-end")}>
      {(isHumanAssistant || isBotAssistant) && (
        <AssistantBadge isHuman={isHumanAssistant} />
      )}
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-3 py-2 shadow-sm",
          isUser && "bg-card border border-border rounded-bl-sm",
          isBotAssistant && "bg-emerald-100/80 text-foreground rounded-br-sm",
          isHumanAssistant && "bg-blue-100/80 text-foreground rounded-br-sm",
          isError && "opacity-70"
        )}
      >
        <p className="text-sm whitespace-pre-wrap break-words">{m.content}</p>

        <div
          className={cn(
            "text-[10px] mt-0.5 flex items-center gap-1 text-muted-foreground",
            !isUser && "justify-end"
          )}
        >
          <span>{formatTime(m.created_at)}</span>

          {isSending && <Loader2 className="h-2.5 w-2.5 animate-spin" />}
          {!isPending && !isUser && <CheckCheck className="h-2.5 w-2.5" />}
          {isError && (
            <span className="text-red-500 flex items-center gap-0.5">
              <AlertCircle className="h-2.5 w-2.5" />
              {pending._errorText ?? "Error al enviar"}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

interface Props {
  messages: MessageOut[];
  pendingMessages?: PendingMsg[];
  loading?: boolean;
}

export function MessageList({ messages, pendingMessages = [], loading }: Props) {
  const endRef = useRef<HTMLDivElement>(null);
  const all: (MessageOut | PendingMsg)[] = [...messages, ...pendingMessages];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [all.length]);

  if (loading) return <MessageListSkeleton rows={6} />;

  if (!all.length) {
    return (
      <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
        Sin mensajes todavia
      </div>
    );
  }

  const groups: { label: string; items: (MessageOut | PendingMsg)[] }[] = [];
  for (const m of all) {
    const label = dateLabel(m.created_at);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(m);
    else groups.push({ label, items: [m] });
  }

  return (
    <ScrollArea className="flex-1 bg-gradient-soft">
      <div className="p-4 space-y-4">
        {groups.map((g, i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-center">
              <span className="text-[10px] font-medium bg-card border border-border rounded-full px-2.5 py-0.5 text-muted-foreground">
                {g.label}
              </span>
            </div>
            {g.items.map((m) => (
              <MessageBubble key={m.id} m={m} />
            ))}
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </ScrollArea>
  );
}
