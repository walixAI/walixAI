import { useState } from "react";
import { Check, Loader2, Pencil, Plus, X } from "lucide-react";
import { toast } from "sonner";
import {
  useProductCategories,
  useCreateProductCategory,
  useUpdateProductCategory,
} from "@/lib/queries/goals";
import type { ProductCategory } from "@/lib/queries/goals";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

// ── Editable row ──────────────────────────────────────────────────────────────

function CategoryRow({ cat }: { cat: ProductCategory }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(cat.name);
  const update = useUpdateProductCategory();

  function handleSaveName() {
    if (!name.trim()) return;
    update.mutate(
      { id: cat.id, patch: { name: name.trim() } },
      {
        onSuccess: () => setEditing(false),
        onError: (e) => toast.error((e as Error).message),
      },
    );
  }

  function handleToggleActive(val: boolean) {
    update.mutate(
      { id: cat.id, patch: { isActive: val } },
      { onError: (e) => toast.error((e as Error).message) },
    );
  }

  return (
    <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/30 transition-colors border-b border-border last:border-0">
      {editing ? (
        <>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-7 text-sm flex-1"
            autoFocus
            onKeyDown={(e) => { if (e.key === "Enter") handleSaveName(); if (e.key === "Escape") { setName(cat.name); setEditing(false); } }}
          />
          <button
            onClick={handleSaveName}
            disabled={update.isPending}
            className="text-emerald-600 hover:text-emerald-700 disabled:opacity-50"
          >
            <Check className="h-4 w-4" />
          </button>
          <button onClick={() => { setName(cat.name); setEditing(false); }} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </>
      ) : (
        <>
          <span className={`text-sm flex-1 ${!cat.isActive ? "line-through text-muted-foreground" : ""}`}>
            {cat.name}
          </span>
          <button
            onClick={() => setEditing(true)}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <Switch
            checked={cat.isActive}
            onCheckedChange={handleToggleActive}
            disabled={update.isPending}
          />
        </>
      )}
    </div>
  );
}

// ── New category form ─────────────────────────────────────────────────────────

function NewCategoryForm() {
  const [name, setName] = useState("");
  const create = useCreateProductCategory();

  function handleCreate() {
    if (!name.trim()) return;
    create.mutate(
      { name: name.trim() },
      {
        onSuccess: () => setName(""),
        onError: (e) => toast.error((e as Error).message),
      },
    );
  }

  return (
    <div className="flex items-center gap-2 px-4 py-3 border-t border-border">
      <Input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Nueva categoría…"
        className="h-8 text-sm flex-1"
        onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
      />
      <Button
        size="sm"
        variant="outline"
        onClick={handleCreate}
        disabled={!name.trim() || create.isPending}
        className="h-8 gap-1"
      >
        {create.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
        Agregar
      </Button>
    </div>
  );
}

// ── Card ──────────────────────────────────────────────────────────────────────

export function ProductCategoriesCard() {
  const { data: categories = [], isPending } = useProductCategories(true);

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold">Categorías de producto</h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          Usadas para agrupar metas por línea de negocio.
        </p>
      </div>

      <div className="rounded-lg border border-border overflow-hidden">
        {isPending ? (
          <div className="flex items-center gap-2 px-4 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
          </div>
        ) : categories.length === 0 ? (
          <p className="px-4 py-6 text-sm text-muted-foreground text-center">
            Sin categorías aún.
          </p>
        ) : (
          categories.map((cat) => <CategoryRow key={cat.id} cat={cat} />)
        )}
        <NewCategoryForm />
      </div>
    </div>
  );
}
