import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from "recharts";
import { usePipelineByStage } from "@/lib/queries/dashboard";

function formatMXN(n: number) {
  return new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN", maximumFractionDigits: 0 }).format(n);
}

const stageColors = [
  "hsl(239 84% 85%)",
  "hsl(239 84% 75%)",
  "hsl(239 84% 65%)",
  "hsl(239 84% 55%)",
  "hsl(239 84% 45%)",
  "hsl(239 84% 35%)",
];

export function PipelineByStageChart() {
  const { data: pipelineByStage = [] } = usePipelineByStage();

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-card">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold">Pipeline por Etapa</h3>
          <p className="text-xs text-muted-foreground">Valor MXN acumulado</p>
        </div>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={pipelineByStage} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
            <XAxis
              dataKey="stage"
              stroke="hsl(var(--muted-foreground))"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              interval={0}
              angle={-15}
              textAnchor="end"
              height={60}
            />
            <YAxis
              stroke="hsl(var(--muted-foreground))"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip
              cursor={{ fill: "hsl(var(--muted))" }}
              contentStyle={{
                background: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: 12,
                fontSize: 12,
              }}
              formatter={(v: number) => [formatMXN(v), "Valor"]}
            />
            <Bar dataKey="value" radius={[8, 8, 0, 0]}>
              {pipelineByStage.map((_, i) => (
                <Cell key={i} fill={stageColors[i % stageColors.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
