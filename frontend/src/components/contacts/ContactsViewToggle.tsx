import { LayoutList, Kanban, LayoutGrid } from "lucide-react";
import { cn } from "@/lib/utils";

export type ViewMode = "list" | "kanban" | "cards";

interface ContactsViewToggleProps {
  value: ViewMode;
  onChange: (mode: ViewMode) => void;
}

const OPTIONS: { value: ViewMode; icon: React.ElementType; label: string }[] = [
  { value: "list",   icon: LayoutList, label: "Lista" },
  { value: "kanban", icon: Kanban,     label: "Kanban" },
  { value: "cards",  icon: LayoutGrid, label: "Tarjetas" },
];

export function ContactsViewToggle({ value, onChange }: ContactsViewToggleProps) {
  return (
    <div data-testid="view-toggle" className="flex items-center gap-0.5 rounded-md border border-border bg-background p-0.5">
      {OPTIONS.map(({ value: v, icon: Icon, label }) => (
        <button
          key={v}
          type="button"
          data-testid={`view-toggle-${v}`}
          aria-label={label}
          title={label}
          onClick={() => onChange(v)}
          className={cn(
            "flex items-center justify-center h-7 w-7 rounded transition-colors",
            value === v
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:text-foreground hover:bg-muted",
          )}
        >
          <Icon className="h-3.5 w-3.5" />
        </button>
      ))}
    </div>
  );
}
