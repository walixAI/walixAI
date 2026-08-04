import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queries/_client";
import { KpiCardsSkeleton, ListRowsSkeleton } from "@/components/walix/Skeletons";
import { widgetRegistry } from "./widgetRegistry";

interface LayoutItem {
  key: string;
  position: number;
  hidden: boolean;
  is_mandatory: boolean;
}

async function fetchLayout(): Promise<LayoutItem[]> {
  return apiRequest<LayoutItem[]>("/api/dashboard/layout");
}

interface Props {
  surface: "dashboard";
}

export function LayoutRenderer({ surface: _surface }: Props) {
  const { data: layout, isLoading } = useQuery({
    queryKey: ["dashboard-layout"],
    queryFn: fetchLayout,
    staleTime: 60_000,
  });

  if (isLoading || !layout) {
    return (
      <div className="space-y-6">
        <KpiCardsSkeleton />
        <ListRowsSkeleton rows={4} />
      </div>
    );
  }

  const visible = layout
    .filter((item) => !item.hidden)
    .sort((a, b) => a.position - b.position);

  return (
    <div className="space-y-6">
      {visible.map((item) => {
        const Widget = widgetRegistry[item.key];
        if (!Widget) {
          console.warn(`[LayoutRenderer] widget key "${item.key}" not found in registry — skipping`);
          return null;
        }
        return <Widget key={item.key} />;
      })}
    </div>
  );
}
