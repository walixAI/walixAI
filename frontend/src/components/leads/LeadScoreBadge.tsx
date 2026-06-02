import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface LeadScoreBadgeProps {
  score: number;
  trend?: "up" | "down" | "flat" | null;
  main_reason?: string;
}

function scoreClasses(score: number): string {
  if (score >= 70) return "bg-success/15 text-success border-success/30";
  if (score >= 40) return "bg-warning/15 text-warning border-warning/30";
  return "bg-danger/15 text-danger border-danger/30";
}

function TrendIcon({ trend }: { trend?: string | null }) {
  if (trend === "up")   return <TrendingUp  className="h-2.5 w-2.5" />;
  if (trend === "down") return <TrendingDown className="h-2.5 w-2.5" />;
  return <Minus className="h-2.5 w-2.5 opacity-50" />;
}

export function LeadScoreBadge({ score, trend, main_reason }: LeadScoreBadgeProps) {
  const badge = (
    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold border leading-none ${scoreClasses(score)}`}>
      <TrendIcon trend={trend} />
      {score}
    </span>
  );

  if (!main_reason) return badge;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{badge}</TooltipTrigger>
      <TooltipContent side="top" className="max-w-[200px] text-xs">
        {main_reason}
      </TooltipContent>
    </Tooltip>
  );
}
