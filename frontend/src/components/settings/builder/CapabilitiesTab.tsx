import { useState } from "react";
import { Plus, Trash2, Loader2, Zap, Globe, MessageSquare } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { cn } from "@/lib/utils";
import { TOOL_LABELS, WRITE_TOOL_NAMES } from "@/lib/constants/copilotTools";
import {
  useCapabilities,
  useToggleCapability,
  useDeleteCapability,
} from "@/lib/queries/walixBuilder";
import { NewCapabilityWizard } from "./NewCapabilityWizard";

interface Props {
  isOwner: boolean;
}

const NATIVE_TOOLS = Object.entries(TOOL_LABELS);

function Badge({ children, variant = "default" }: { children: React.ReactNode; variant?: "default" | "write" | "channel" | "confirm" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold",
        variant === "write" && "bg-orange-100 text-orange-700",
        variant === "channel" && "bg-blue-100 text-blue-700",
        variant === "confirm" && "bg-yellow-100 text-yellow-700",
        variant === "default" && "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

export function CapabilitiesTab({ isOwner }: Props) {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const { data: capabilities = [], isLoading } = useCapabilities();
  const toggleMutation = useToggleCapability();
  const deleteMutation = useDeleteCapability();

  async function handleToggle(id: string, current: boolean) {
    try {
      await toggleMutation.mutateAsync({ id, is_active: !current });
    } catch {
      toast.error("Error al actualizar la capacidad");
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    try {
      await deleteMutation.mutateAsync(deleteTarget.id);
      toast.success("Capacidad eliminada");
      setDeleteTarget(null);
    } catch {
      toast.error("Error al eliminar");
    }
  }

  return (
    <div className="space-y-8">
      {/* § Nativas */}
      <div className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold">Capacidades nativas del Copiloto</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Herramientas integradas disponibles siempre. No requieren configuración.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {NATIVE_TOOLS.map(([key, label]) => (
            <div
              key={key}
              className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2"
            >
              <Zap className="h-3 w-3 text-muted-foreground shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-medium truncate">{label}</p>
                <p className="text-[10px] text-muted-foreground">
                  {WRITE_TOOL_NAMES.has(key) ? "escritura" : "lectura"}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* § Personalizadas */}
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold">Capacidades personalizadas</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Recetas creadas para este tenant via el Walix Builder.
            </p>
          </div>
          {isOwner && (
            <Button size="sm" className="gap-1.5 shrink-0" onClick={() => setWizardOpen(true)}>
              <Plus className="h-3.5 w-3.5" />
              Nueva capacidad
            </Button>
          )}
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Cargando capacidades…
          </div>
        ) : capabilities.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center border border-dashed border-border rounded-xl">
            <Zap className="h-8 w-8 text-muted-foreground/40" />
            <div className="space-y-1">
              <p className="text-sm font-medium">Sin capacidades personalizadas</p>
              <p className="text-xs text-muted-foreground">
                {isOwner
                  ? "Crea tu primera capacidad con el Walix Builder."
                  : "El owner del workspace puede crear capacidades desde aquí."}
              </p>
            </div>
            {isOwner && (
              <Button size="sm" onClick={() => setWizardOpen(true)}>
                <Plus className="h-3.5 w-3.5 mr-1.5" />
                Nueva capacidad
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {capabilities.map((cap) => {
              const steps = cap.recipe_json?.steps ?? [];
              return (
                <div
                  key={cap.id}
                  className={cn(
                    "rounded-xl border border-border bg-card p-4 space-y-3 transition-opacity",
                    !cap.is_active && "opacity-60",
                  )}
                >
                  {/* Header row */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-semibold truncate">{cap.name}</p>
                        <Badge>{cap.kind}</Badge>
                        {cap.require_confirmation && (
                          <Badge variant="confirm">confirmación</Badge>
                        )}
                        {cap.channels.map((ch) => (
                          <Badge key={ch} variant="channel">
                            {ch === "web" ? (
                              <Globe className="h-2.5 w-2.5 mr-0.5 inline" />
                            ) : (
                              <MessageSquare className="h-2.5 w-2.5 mr-0.5 inline" />
                            )}
                            {ch}
                          </Badge>
                        ))}
                      </div>
                      {cap.description && (
                        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                          {cap.description}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {isOwner && (
                        <>
                          <Switch
                            checked={cap.is_active}
                            onCheckedChange={() => handleToggle(cap.id, cap.is_active)}
                            disabled={toggleMutation.isPending}
                          />
                          <button
                            onClick={() => setDeleteTarget({ id: cap.id, name: cap.name })}
                            className="text-muted-foreground hover:text-danger transition-colors"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Steps */}
                  {steps.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {steps.map((step, i) => (
                        <span
                          key={i}
                          className={cn(
                            "inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium border",
                            WRITE_TOOL_NAMES.has(step.tool)
                              ? "bg-orange-50 border-orange-200 text-orange-700"
                              : "bg-muted border-border text-muted-foreground",
                          )}
                        >
                          <span className="font-mono text-[9px] opacity-70">{i + 1}.</span>
                          {TOOL_LABELS[step.tool] ?? step.tool}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Trigger phrases */}
                  {cap.trigger_phrases.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {cap.trigger_phrases.map((phrase) => (
                        <span
                          key={phrase}
                          className="rounded-full bg-primary/8 text-primary px-2 py-0.5 text-[10px] font-medium"
                        >
                          "{phrase}"
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Scope + limit */}
                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                    <span>
                      Scope:{" "}
                      {cap.scope_type === "all"
                        ? "todos"
                        : cap.scope_type === "role"
                        ? `roles: ${cap.scope_roles.join(", ")}`
                        : "usuarios específicos"}
                    </span>
                    {cap.daily_limit !== null && (
                      <span>· Límite: {cap.daily_limit}/día</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <NewCapabilityWizard open={wizardOpen} onClose={() => setWizardOpen(false)} />

      <ConfirmDialog
        open={!!deleteTarget}
        title="Eliminar capacidad"
        description={`¿Eliminar "${deleteTarget?.name}"? Esta acción no se puede deshacer.`}
        confirmLabel="Eliminar"
        destructive
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
