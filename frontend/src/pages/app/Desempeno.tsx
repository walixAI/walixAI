import { useAuth } from "@/hooks/useAuth";
import { LayoutRenderer } from "@/components/dashboard/LayoutRenderer";
import { ShieldOff } from "lucide-react";

const OWNER_ROLES = new Set(["owner", "platform_owner"]);

export default function Desempeno() {
  const { user } = useAuth();

  if (!user || !OWNER_ROLES.has((user as any).role ?? "")) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
        <ShieldOff className="h-10 w-10 text-muted-foreground" />
        <h2 className="text-lg font-semibold">Acceso restringido</h2>
        <p className="text-sm text-muted-foreground max-w-xs">
          Esta sección está disponible solo para owners del tenant.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-[1400px]">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight">Desempeño</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Métricas de equipo, ROI del copiloto IA y forecast de leads
        </p>
      </div>

      <LayoutRenderer panelKey="desempeno" />
    </div>
  );
}
