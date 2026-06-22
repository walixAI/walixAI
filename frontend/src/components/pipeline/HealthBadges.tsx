import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { HEALTH_META, type HealthInfo } from "@/lib/dealHealth";

interface Props {
  health: HealthInfo;
  className?: string;
}

export function HealthBadges({ health, className }: Props) {
  if (health.signals.length === 0) {
    return (
      <span className={cn("text-[10px] font-medium text-muted-foreground", className)}>
        {health.daysInStage}d en etapa
      </span>
    );
  }
  return (
    <TooltipProvider delayDuration={150}>
      <div className={cn("flex items-center gap-1", className)}>
        {health.signals.map((s) => {
          const meta = HEALTH_META[s];
          return (
            <Tooltip key={s}>
              <TooltipTrigger asChild>
                <span
                  className={cn(
                    "text-[10px] font-semibold border rounded-full px-1.5 py-0.5 leading-none flex items-center gap-0.5",
                    meta.className,
                  )}
                >
                  <span className="text-[10px]">{meta.emoji}</span>
                  {meta.label}
                </span>
              </TooltipTrigger>
              <TooltipContent side="top" className="text-xs">
                {meta.tooltip(health)}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
