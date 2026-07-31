import { useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { Plus, Pencil, Check, X } from "lucide-react";
import {
  useExpenseCategories,
  useCreateExpenseCategory,
  useUpdateExpenseCategory,
} from "@/lib/queries/finance";
import type { ExpenseCategory } from "@/lib/queries/finance";

// ── Inline edit row ───────────────────────────────────────────────────────────

function CategoryRow({ cat }: { cat: ExpenseCategory }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(cat.name);
  const update = useUpdateExpenseCategory();

  function save() {
    const trimmed = name.trim();
    if (!trimmed) return;
    update.mutate(
      { id: cat.id, patch: { name: trimmed } },
      {
        onSuccess: () => setEditing(false),
        onError: (e) => toast.error((e as Error).message),
      },
    );
  }

  function toggleActive() {
    update.mutate(
      { id: cat.id, patch: { isActive: !cat.isActive } },
      { onError: (e) => toast.error((e as Error).message) },
    );
  }

  return (
    <div className="flex items-center gap-2 py-2 px-3 hover:bg-muted/40 rounded-lg transition-colors">
      {editing ? (
        <>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-7 text-sm flex-1"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") { setName(cat.name); setEditing(false); }
            }}
          />
          <button
            type="button"
            onClick={save}
            className="text-primary hover:opacity-80 shrink-0"
            aria-label="Guardar"
          >
            <Check className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => { setName(cat.name); setEditing(false); }}
            className="text-muted-foreground hover:opacity-80 shrink-0"
            aria-label="Cancelar"
          >
            <X className="h-4 w-4" />
          </button>
        </>
      ) : (
        <>
          <span className={`flex-1 text-sm truncate ${!cat.isActive ? "text-muted-foreground line-through" : "text-foreground"}`}>
            {cat.name}
          </span>
          <span className="text-xs text-muted-foreground capitalize shrink-0">{cat.kind}</span>
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-muted-foreground hover:text-primary shrink-0"
            aria-label="Editar"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <Switch
            checked={cat.isActive}
            onCheckedChange={toggleActive}
            aria-label={cat.isActive ? "Desactivar categoría" : "Activar categoría"}
            className="shrink-0"
          />
        </>
      )}
    </div>
  );
}

// ── New category form ─────────────────────────────────────────────────────────

function NewCategoryForm() {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"fijo" | "variable">("variable");
  const create = useCreateExpenseCategory();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    create.mutate(
      { name: trimmed, kind },
      {
        onSuccess: () => { setName(""); toast.success("Categoría creada"); },
        onError: (e) => toast.error((e as Error).message),
      },
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-2 pt-3 border-t border-border mt-2"
    >
      <div className="flex-1 space-y-1">
        <Label className="text-xs text-muted-foreground">Nueva categoría</Label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nombre..."
          className="h-8 text-sm"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs text-muted-foreground">Tipo</Label>
        <Select value={kind} onValueChange={(v) => setKind(v as "fijo" | "variable")}>
          <SelectTrigger className="h-8 w-28 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="fijo">Fijo</SelectItem>
            <SelectItem value="variable">Variable</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Button
        type="submit"
        size="sm"
        className="h-8 shrink-0"
        disabled={create.isPending || !name.trim()}
      >
        <Plus className="h-4 w-4 mr-1" />Agregar
      </Button>
    </form>
  );
}

// ── Dialog trigger ────────────────────────────────────────────────────────────

export function ExpenseCategoriesManager() {
  const [open, setOpen] = useState(false);
  const { data: categories = [], isPending } = useExpenseCategories(true);

  const sorted = [...categories].sort((a, b) => {
    if (a.isActive !== b.isActive) return a.isActive ? -1 : 1;
    if (a.kind !== b.kind) return a.kind.localeCompare(b.kind);
    return a.name.localeCompare(b.name);
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">Categorías</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Categorías de gasto</DialogTitle>
        </DialogHeader>
        <div className="max-h-72 overflow-y-auto space-y-0.5 pr-1">
          {isPending ? (
            <p className="text-sm text-muted-foreground py-6 text-center">Cargando…</p>
          ) : sorted.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              Sin categorías todavía
            </p>
          ) : (
            sorted.map((cat) => <CategoryRow key={cat.id} cat={cat} />)
          )}
        </div>
        <NewCategoryForm />
      </DialogContent>
    </Dialog>
  );
}
