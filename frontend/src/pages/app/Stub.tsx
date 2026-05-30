import { type LucideIcon } from "lucide-react";
import { WBadge } from "@/components/walix/Badge";

interface Props {
  icon: LucideIcon;
  title: string;
  description: string;
  badge?: string;
}

export function Stub({ icon: Icon, title, description, badge }: Props) {
  return (
    <div className="max-w-[1400px] space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        </div>
        {badge && <WBadge variant="brand">{badge}</WBadge>}
      </div>

      <div className="rounded-2xl border border-dashed border-border bg-card p-12 text-center">
        <div className="h-16 w-16 mx-auto rounded-2xl bg-gradient-brand grid place-items-center shadow-glow mb-4">
          <Icon className="h-8 w-8 text-primary-foreground" />
        </div>
        <h2 className="text-lg font-semibold">Modulo en construccion</h2>
        <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
          Esta seccion estara disponible en proximas versiones de Walix.ai.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div
            key={i}
            className="rounded-xl border border-border bg-card p-4 shadow-card hover:shadow-card-hover transition-all"
          >
            <div className="h-3 w-1/3 bg-muted rounded mb-3" />
            <div className="h-2 w-full bg-muted/60 rounded mb-1.5" />
            <div className="h-2 w-4/5 bg-muted/60 rounded mb-3" />
            <div className="flex gap-2">
              <WBadge variant="info">activo</WBadge>
              <WBadge variant="neutral">demo</WBadge>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
