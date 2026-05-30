import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props { className?: string; collapsed?: boolean }

export function Logo({ className, collapsed }: Props) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="relative h-8 w-8 rounded-xl bg-gradient-brand grid place-items-center shadow-glow">
        <Sparkles className="h-4 w-4 text-primary-foreground" strokeWidth={2.5} />
      </div>
      {!collapsed && (
        <div className="flex items-baseline gap-0.5 leading-none">
          <span className="text-lg font-bold tracking-tight">Walix</span>
          <span className="text-lg font-bold text-gradient-brand">.ai</span>
        </div>
      )}
    </div>
  );
}
