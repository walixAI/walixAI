import { Bot, User, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  currentHandler: "bot" | "human" | null;
  handlerName: string;
  onHandoff: () => void;
  onReturnToBot: () => void;
  loading?: boolean;
}

export function ConversationBanner({
  currentHandler,
  handlerName,
  onHandoff,
  onReturnToBot,
  loading,
}: Props) {
  const isHuman = currentHandler === "human";

  return (
    <div
      className={cn(
        "flex items-center gap-2 px-4 py-2 text-sm border-b border-border",
        isHuman
          ? "bg-accent/10 text-accent"
          : "bg-primary/10 text-primary"
      )}
    >
      {isHuman ? (
        <User className="h-3.5 w-3.5 shrink-0" />
      ) : (
        <Bot className="h-3.5 w-3.5 shrink-0" />
      )}

      <span className="flex-1 text-xs font-medium">
        {isHuman
          ? `${handlerName} tiene el control`
          : "Bot activo — respondiendo automáticamente"}
      </span>

      {isHuman ? (
        <Button
          variant="outline"
          size="sm"
          className="h-6 text-[11px] px-2 border-accent/40 text-accent hover:bg-accent/10"
          onClick={onReturnToBot}
          disabled={loading}
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Devolver al bot"}
        </Button>
      ) : (
        <Button
          size="sm"
          className="h-6 text-[11px] px-2 bg-success hover:bg-success/90 text-success-foreground"
          onClick={onHandoff}
          disabled={loading}
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Tomar control"}
        </Button>
      )}
    </div>
  );
}
