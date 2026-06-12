import { Skeleton } from "@/components/ui/skeleton";

export function ContactDetailSkeleton() {
  return (
    <div data-testid="contact-detail-skeleton" className="grid gap-4 p-4" style={{ gridTemplateColumns: "256px 1fr 256px" }}>
      {/* Left panel */}
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <Skeleton className="h-14 w-14 rounded-full shrink-0" />
          <div className="space-y-1.5 flex-1">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="space-y-1">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-8 w-full" />
          </div>
        ))}
      </div>

      {/* Center */}
      <div className="space-y-4">
        <div className="flex gap-2">
          {["Resumen", "Conversaciones", "Actividades"].map((t) => (
            <Skeleton key={t} className="h-8 w-28 rounded-full" />
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-48 w-full rounded-xl" />
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex gap-3">
            <Skeleton className="h-8 w-8 rounded-full shrink-0" />
            <div className="space-y-1.5 flex-1">
              <Skeleton className="h-3 w-1/3" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          </div>
        ))}
      </div>

      {/* Right panel */}
      <div className="space-y-4">
        <Skeleton className="h-4 w-20" />
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full rounded-xl" />
        ))}
        <Skeleton className="h-4 w-24 mt-4" />
        <Skeleton className="h-28 w-full rounded-xl" />
      </div>
    </div>
  );
}
