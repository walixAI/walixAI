import { Bot, Calendar, CheckSquare, Clock, Mail, MessageSquare, Phone } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface LastActivityCellProps {
  lastActivitySummary: string | null;
  lastActivityAt: string | null;
}

function getIcon(summary: string | null) {
  if (!summary) return <Clock className="h-3.5 w-3.5 shrink-0" />;
  const s = summary.toLowerCase();
  if (s.startsWith("llamada") || s.startsWith("call")) return <Phone className="h-3.5 w-3.5 shrink-0" />;
  if (s.startsWith("nota") || s.startsWith("note")) return <MessageSquare className="h-3.5 w-3.5 shrink-0" />;
  if (s.startsWith("tarea") || s.startsWith("task")) return <CheckSquare className="h-3.5 w-3.5 shrink-0" />;
  if (s.startsWith("reunión") || s.startsWith("meeting") || s.startsWith("reunion")) return <Calendar className="h-3.5 w-3.5 shrink-0" />;
  if (s.startsWith("email")) return <Mail className="h-3.5 w-3.5 shrink-0" />;
  return <Bot className="h-3.5 w-3.5 shrink-0" />;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const d = Math.floor(diff / 86_400_000);
  if (d === 0) return "Hoy";
  if (d === 1) return "Ayer";
  if (d < 30) return `hace ${d}d`;
  if (d < 365) return `hace ${Math.floor(d / 30)}m`;
  return `hace ${Math.floor(d / 365)}a`;
}

function formatExact(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("es-MX", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function LastActivityCell({ lastActivitySummary, lastActivityAt }: LastActivityCellProps) {
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            data-testid="last-activity-cell"
            data-empty={!lastActivitySummary && !lastActivityAt ? "true" : undefined}
            className="text-xs text-muted-foreground cursor-default select-none"
          >
            {formatRelative(lastActivityAt)}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[280px] p-3 space-y-1.5">
          {lastActivitySummary ? (
            <>
              <div className="flex items-start gap-1.5 text-xs">
                {getIcon(lastActivitySummary)}
                <span className="leading-snug">{lastActivitySummary}</span>
              </div>
              {lastActivityAt && (
                <p className="text-[11px] text-muted-foreground">{formatExact(lastActivityAt)}</p>
              )}
            </>
          ) : (
            <p className="text-xs text-muted-foreground">Sin actividades registradas</p>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
