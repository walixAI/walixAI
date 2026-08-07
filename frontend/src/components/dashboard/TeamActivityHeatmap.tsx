import { Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { useReportsExtra, type ActivityHeatmapCell } from "@/lib/queries/reports";

function intensity(count: number, max: number): string {
  if (max === 0 || count === 0) return "bg-muted";
  const ratio = count / max;
  if (ratio < 0.25) return "bg-primary/20";
  if (ratio < 0.5) return "bg-primary/40";
  if (ratio < 0.75) return "bg-primary/60";
  return "bg-primary/90";
}

function shortDay(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("es-MX", { weekday: "short", day: "numeric" });
}

export function TeamActivityHeatmap() {
  const { data, isLoading } = useReportsExtra(30);

  const cells = data?.activity_heatmap ?? [];

  const users = [...new Map(cells.map((c) => [c.user_id, c.user_name])).entries()].map(
    ([id, name]) => ({ id, name }),
  );
  const days = [...new Set(cells.map((c) => c.day))].sort();

  const cellMap = new Map<string, ActivityHeatmapCell>();
  for (const c of cells) cellMap.set(`${c.user_id}:${c.day}`, c);

  const allTotals = cells.map((c) => c.whatsapp_count + c.activity_count);
  const maxTotal = allTotals.length > 0 ? Math.max(...allTotals) : 0;

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center gap-2 mb-4">
        <div className="h-8 w-8 grid place-items-center rounded-lg bg-primary/10 text-primary">
          <Activity className="h-4 w-4" />
        </div>
        <h3 className="text-sm font-semibold">Actividad del equipo</h3>
        {data && (
          <span className="ml-auto text-xs text-muted-foreground">Últimos {data.period_days} días</span>
        )}
      </div>

      {isLoading || !data ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-8 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : users.length === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center">Sin actividad registrada en este período</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr>
                <th className="text-left font-medium text-muted-foreground pb-2 pr-3 min-w-[100px]">
                  Usuario
                </th>
                {days.slice(-14).map((d) => (
                  <th
                    key={d}
                    className="text-center font-medium text-muted-foreground pb-2 px-0.5 min-w-[32px]"
                    title={d}
                  >
                    {shortDay(d)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td className="pr-3 py-0.5 font-medium truncate max-w-[100px]">{u.name}</td>
                  {days.slice(-14).map((d) => {
                    const c = cellMap.get(`${u.id}:${d}`);
                    const total = c ? c.whatsapp_count + c.activity_count : 0;
                    return (
                      <td key={d} className="px-0.5 py-0.5 text-center">
                        <div
                          className={cn(
                            "h-6 w-7 rounded mx-auto",
                            intensity(total, maxTotal),
                          )}
                          title={
                            c
                              ? `WA: ${c.whatsapp_count} · Act: ${c.activity_count}`
                              : "Sin actividad"
                          }
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            <span>Menos</span>
            {["bg-muted", "bg-primary/20", "bg-primary/40", "bg-primary/60", "bg-primary/90"].map((cls) => (
              <div key={cls} className={cn("h-3 w-3 rounded", cls)} />
            ))}
            <span>Más</span>
            <span className="ml-2 opacity-60">(WA + actividades)</span>
          </div>
        </div>
      )}
    </div>
  );
}
