import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function LoadingSpinner({ className, label }: { className?: string; label?: string }) {
  return (
    <div className={cn("flex items-center justify-center gap-2 text-muted-foreground", className)}>
      <Loader2 className="h-4 w-4 animate-spin text-primary" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}
