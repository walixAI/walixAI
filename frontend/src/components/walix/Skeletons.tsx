import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function KpiCardsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-border bg-card p-5 shadow-card"
        >
          <div className="flex items-start justify-between">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-9 w-9 rounded-lg" />
          </div>
          <Skeleton className="mt-4 h-7 w-32" />
          <Skeleton className="mt-2 h-3 w-20" />
        </div>
      ))}
    </div>
  );
}

export function ListRowsSkeleton({
  rows = 5,
  showAvatar = true,
  className,
}: { rows?: number; showAvatar?: boolean; className?: string }) {
  return (
    <div className={cn("divide-y divide-border", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-5 py-3">
          {showAvatar && <Skeleton className="h-9 w-9 rounded-full shrink-0" />}
          <div className="flex-1 min-w-0 space-y-2">
            <Skeleton className="h-3.5 w-3/4 max-w-[260px]" />
            <Skeleton className="h-3 w-24" />
          </div>
          <Skeleton className="h-7 w-7 rounded-lg shrink-0" />
        </div>
      ))}
    </div>
  );
}

export function ConversationListSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="divide-y divide-border">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3">
          <Skeleton className="h-10 w-10 rounded-full shrink-0" />
          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex items-center justify-between">
              <Skeleton className="h-3.5 w-32" />
              <Skeleton className="h-3 w-10" />
            </div>
            <Skeleton className="h-3 w-3/4" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function MessageListSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="flex-1 p-6 space-y-4">
      {Array.from({ length: rows }).map((_, i) => {
        const mine = i % 2 === 1;
        const w = ["w-48", "w-64", "w-40", "w-56", "w-72"][i % 5];
        return (
          <div key={i} className={cn("flex", mine ? "justify-end" : "justify-start")}>
            <Skeleton className={cn("h-12 rounded-2xl", w)} />
          </div>
        );
      })}
    </div>
  );
}
