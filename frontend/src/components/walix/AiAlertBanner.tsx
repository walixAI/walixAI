import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface Props {
  variant?: "warning" | "danger" | "info";
  icon?: React.ReactNode;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  dismissible?: boolean;
  className?: string;
}

/**
 * <AiAlertBanner /> — banner accionable para alertas detectadas por reglas/IA.
 */
export function AiAlertBanner({
  variant = "warning", icon, title, description,
  actionLabel, onAction, dismissible = true, className,
}: Props) {
  const [open, setOpen] = useState(true);
  if (!open) return null;

  const palette =
    variant === "danger"
      ? "bg-danger/5 border-danger/30 text-danger"
      : variant === "info"
        ? "bg-primary/5 border-primary/20 text-primary"
        : "bg-warning/10 border-warning/30 text-warning-foreground";

  const iconColor =
    variant === "danger" ? "text-danger" : variant === "info" ? "text-primary" : "text-warning";

  return (
    <div className={cn("rounded-xl border px-3 py-2.5 flex items-center gap-3", palette, className)}>
      <div className={cn("shrink-0", iconColor)}>
        {icon ?? <AlertTriangle className="h-4 w-4" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-foreground">{title}</div>
        {description && <div className="text-xs text-muted-foreground mt-0.5">{description}</div>}
      </div>
      {actionLabel && onAction && (
        <Button size="sm" variant="outline" className="h-7 text-xs shrink-0" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
      {dismissible && (
        <button
          onClick={() => setOpen(false)}
          className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Cerrar alerta"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
