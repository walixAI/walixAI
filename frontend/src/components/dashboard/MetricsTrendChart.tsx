import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";

interface MetricsTrendChartProps {
  branchId?: string | null;
}

type Period = "week" | "month" | "quarter";

const PERIOD_LABELS: Record<Period, string> = {
  week: "Semana",
  month: "Mes",
  quarter: "Trimestre",
};

export function MetricsTrendChart({ branchId }: MetricsTrendChartProps) {
  const [period, setPeriod] = useState<Period>("month");

  const { data, isLoading } = useQuery({
    queryKey: ["metrics-dashboard", period, branchId],
    queryFn: () => api.getMetricsDashboard({ period, branch_id: branchId ?? undefined }),
    enabled: !!branchId,
    staleTime: 120_000,
  });

  const chartData = (data?.daily ?? []).map((d) => ({
    date: new Date(d.metric_date).toLocaleDateString("es-MX", { day: "numeric", month: "short" }),
    Creados: d.leads_created,
    Calificados: d.leads_qualified,
    Ganados: d.leads_won,
  }));

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Tendencia de leads</p>
        </div>
        <Tabs value={period} onValueChange={(v) => setPeriod(v as Period)}>
          <TabsList className="h-7">
            {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => (
              <TabsTrigger key={p} value={p} className="text-xs px-2.5 h-6">
                {PERIOD_LABELS[p]}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {isLoading ? (
        <div className="h-[240px] flex items-center justify-center">
          <div className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        </div>
      ) : !branchId ? (
        <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">
          Sin sucursal seleccionada
        </div>
      ) : chartData.length === 0 ? (
        <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">
          Sin datos para este período — los KPIs se calculan a las 00:00 h
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                background: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "8px",
                fontSize: 12,
              }}
            />
            <Legend
              iconType="circle"
              iconSize={7}
              wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            />
            <Line
              type="monotone"
              dataKey="Creados"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
            <Line
              type="monotone"
              dataKey="Calificados"
              stroke="hsl(var(--accent))"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
            <Line
              type="monotone"
              dataKey="Ganados"
              stroke="hsl(var(--success))"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
