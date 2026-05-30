import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { MessageOut } from "@/lib/api";
import { MessageListSkeleton } from "@/components/walix/Skeletons";

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

function MessageBubble({ m }: { m: MessageOut }) {
  const isUser = m.role === "user";
  const isSystem = m.role === "system";

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
    <div className={cn("flex", isUser ? "justify-start" : "justify-end")}>
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-3 py-2 shadow-sm",
          isUser
            ? "bg-card border border-border rounded-bl-sm"
            : "bg-primary/10 text-foreground rounded-br-sm"
        )}
      >
        <p className="text-sm whitespace-pre-wrap break-words">{m.content}</p>
        <div
          className={cn(
            "text-[10px] mt-0.5 flex items-center gap-1",
            "text-muted-foreground",
            !isUser && "justify-end"
          )}
        >
          <span>{formatTime(m.created_at)}</span>
        </div>
      </div>
    </div>
  );
}

interface Props {
  messages: MessageOut[];
  loading?: boolean;
}

export function MessageList({ messages, loading }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  if (loading) {
    return <MessageListSkeleton rows={6} />;
  }

  if (!messages.length) {
    return (
      <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
        Sin mensajes todavia
      </div>
    );
  }

  // group by day
  const groups: { label: string; items: MessageOut[] }[] = [];
  for (const m of messages) {
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
