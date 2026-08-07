import { useState } from "react";
import { toast } from "sonner";
import { Loader2, LayoutGrid, Star, Bookmark, Folder, Target, Zap, Users, BarChart3 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useCreatePanel, type PanelOut } from "@/lib/queries/panels";

const ICON_OPTIONS = [
  { key: "layout-grid",  Icon: LayoutGrid,  label: "Grid" },
  { key: "star",         Icon: Star,         label: "Estrella" },
  { key: "bookmark",     Icon: Bookmark,     label: "Marcador" },
  { key: "folder",       Icon: Folder,       label: "Carpeta" },
  { key: "target",       Icon: Target,       label: "Meta" },
  { key: "zap",          Icon: Zap,          label: "Rayo" },
  { key: "users",        Icon: Users,        label: "Equipo" },
  { key: "bar-chart-3",  Icon: BarChart3,    label: "Gráfica" },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (panel: PanelOut) => void;
}

export function CreatePanelDialog({ open, onOpenChange, onCreated }: Props) {
  const [name, setName] = useState("");
  const [selectedIcon, setSelectedIcon] = useState<string | null>(null);

  const createPanel = useCreatePanel();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const panel = await createPanel.mutateAsync({ name: name.trim(), icon: selectedIcon });
      toast.success(`Panel "${panel.name}" creado`);
      setName("");
      setSelectedIcon(null);
      onOpenChange(false);
      onCreated(panel);
    } catch (err: any) {
      toast.error("Error al crear el panel", { description: err?.message });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Nuevo panel</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          <div className="space-y-1.5">
            <Label htmlFor="panel-name">Nombre</Label>
            <Input
              id="panel-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Mi panel"
              autoFocus
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label>Ícono (opcional)</Label>
            <div className="grid grid-cols-4 gap-2">
              {ICON_OPTIONS.map(({ key, Icon, label }) => (
                <button
                  key={key}
                  type="button"
                  title={label}
                  onClick={() => setSelectedIcon(selectedIcon === key ? null : key)}
                  className={cn(
                    "flex flex-col items-center gap-1 rounded-lg border p-2.5 transition-colors text-xs",
                    selectedIcon === key
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:border-primary/50 hover:bg-muted text-muted-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </div>

          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={!name.trim() || createPanel.isPending}>
              {createPanel.isPending && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
              Crear
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
