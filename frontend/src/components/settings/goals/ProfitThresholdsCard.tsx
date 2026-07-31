import { useEffect, useState } from "react";
import { Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { useFinanceSettings, useUpdateFinanceSettings } from "@/lib/queries/profitability";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

export function ProfitThresholdsCard() {
  const { user } = useAuth();
  const isOwner = user?.role === "owner" || user?.role === "platform_owner";

  const { data: settings, isPending } = useFinanceSettings();
  const update = useUpdateFinanceSettings();

  const [countBiz, setCountBiz] = useState(false);
  const [green, setGreen] = useState("20");
  const [yellow, setYellow] = useState("10");
  const [orange, setOrange] = useState("0");

  useEffect(() => {
    if (!settings) return;
    setCountBiz(settings.countBusinessDays);
    setGreen(String(settings.profitThresholds.green));
    setYellow(String(settings.profitThresholds.yellow));
    setOrange(String(settings.profitThresholds.orange));
  }, [settings]);

  function handleSave() {
    const g = parseFloat(green);
    const y = parseFloat(yellow);
    const o = parseFloat(orange);
    if ([g, y, o].some(isNaN)) {
      toast.error("Los umbrales deben ser números");
      return;
    }
    update.mutate(
      { countBusinessDays: countBiz, profitThresholds: { green: g, yellow: y, orange: o } },
      {
        onSuccess: () => toast.success("Configuración guardada"),
        onError: (e) => toast.error((e as Error).message),
      },
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold">Configuración de rentabilidad</h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          Umbrales de margen de utilidad y conteo de días hábiles.
        </p>
      </div>

      {isPending ? (
        <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
        </div>
      ) : (
        <fieldset disabled={!isOwner} className="space-y-5">
          {/* Count business days */}
          <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3">
            <div>
              <Label className="text-sm font-medium">Contar solo días hábiles</Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Excluye sábados y domingos al calcular el ritmo diario de ventas.
              </p>
            </div>
            <Switch
              checked={countBiz}
              onCheckedChange={setCountBiz}
              disabled={!isOwner}
            />
          </div>

          {/* Thresholds */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Umbrales de margen (%)</Label>
            <div className="grid grid-cols-3 gap-3">
              {(
                [
                  { label: "Verde (bueno)", color: "text-emerald-600", val: green, set: setGreen },
                  { label: "Amarillo (alerta)", color: "text-yellow-600", val: yellow, set: setYellow },
                  { label: "Naranja (riesgo)", color: "text-orange-600", val: orange, set: setOrange },
                ] as const
              ).map(({ label, color, val, set }) => (
                <div key={label} className="space-y-1.5">
                  <Label className={`text-xs font-medium ${color}`}>{label}</Label>
                  <Input
                    type="number"
                    value={val}
                    onChange={(e) => set(e.target.value)}
                    disabled={!isOwner}
                    className="h-8 text-sm"
                    step="1"
                    min="0"
                    max="100"
                  />
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              "Verde" si el margen es ≥ verde%. "Amarillo" si es ≥ amarillo%. "Naranja" si es ≥ naranja%.
            </p>
          </div>

          {!isOwner && (
            <p className="text-xs text-muted-foreground italic">
              Solo el propietario puede modificar esta configuración.
            </p>
          )}

          {isOwner && (
            <Button
              size="sm"
              onClick={handleSave}
              disabled={update.isPending}
              className="gap-1.5"
            >
              {update.isPending
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <Save className="h-3.5 w-3.5" />}
              Guardar
            </Button>
          )}
        </fieldset>
      )}
    </div>
  );
}
