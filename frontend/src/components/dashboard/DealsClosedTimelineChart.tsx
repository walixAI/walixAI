import { ArrowUpRight } from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import { useDealsClosedTimeline } from "@/lib/queries/dashboard";

function formatMXN(n: number) {
  return new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 }).format(n);
}

export function DealsClosedTimelineChart() {
  const { data: dealsTimeline = [] } = useDealsClosedTimeline(30);

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold">Oportunidades cerradas</h3>
          <p className="text-xs text-muted-foreground">Últimos 30 días</p>
        </div>
        <span className="text-xs font-semibold text-success inline-flex items-center gap-0.5">
          <ArrowUpRight className="h-3 w-3" /> +18%
        </span>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={dealsTimeline} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="gClosed" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="hsl(var(--accent))" stopOpacity={0.3} />
                <stop offset="100%" stopColor="hsl(var(--accent))" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
            <XAxis
              dataKey="day"
              stroke="hsl(var(--muted-foreground))"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              interval={4}
            />
            <YAxis
              stroke="hsl(var(--muted-foreground))"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip
              contentStyle={{
                background: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: 12,
                fontSize: 12,
              }}
              formatter={(v: number) => [formatMXN(v), "Cerrado"]}
              labelFormatter={(l) => `Día ${l}`}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="hsl(var(--accent))"
              strokeWidth={2.5}
              fill="url(#gClosed)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
