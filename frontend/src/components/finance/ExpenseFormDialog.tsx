import { useState, useEffect } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { useExpenseCategories, useCreateExpense } from "@/lib/queries/finance";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ExpenseFormDialog({ open, onOpenChange }: Props) {
  const [kind, setKind] = useState<"fijo" | "variable">("variable");
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [incurredAt, setIncurredAt] = useState(new Date().toISOString().slice(0, 10));
  const [description, setDescription] = useState("");

  const { data: categories = [] } = useExpenseCategories();
  const createExpense = useCreateExpense();

  const filteredCategories = categories.filter((c) => c.kind === kind && c.isActive);

  useEffect(() => {
    setCategoryId("");
  }, [kind]);

  function resetForm() {
    setKind("variable");
    setCategoryId("");
    setAmount("");
    setIncurredAt(new Date().toISOString().slice(0, 10));
    setDescription("");
  }

  function handleOpenChange(v: boolean) {
    if (!v) resetForm();
    onOpenChange(v);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const amountNum = parseFloat(amount);
    if (!amountNum || amountNum <= 0) {
      toast.error("El monto debe ser mayor a $0");
      return;
    }
    if (!categoryId) {
      toast.error("Selecciona una categoría");
      return;
    }
    createExpense.mutate(
      { amount: amountNum, kind, categoryId, incurredAt, description: description || null },
      {
        onSuccess: () => { toast.success("Gasto registrado"); handleOpenChange(false); },
        onError: (err) => toast.error((err as Error).message ?? "Error al guardar"),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Nuevo gasto</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          {/* Tipo */}
          <div className="space-y-2">
            <Label>Tipo</Label>
            <RadioGroup
              value={kind}
              onValueChange={(v) => setKind(v as "fijo" | "variable")}
              className="flex gap-6"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="fijo" id="ef-kind-fijo" />
                <Label htmlFor="ef-kind-fijo" className="cursor-pointer font-normal">Fijo</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="variable" id="ef-kind-variable" />
                <Label htmlFor="ef-kind-variable" className="cursor-pointer font-normal">Variable</Label>
              </div>
            </RadioGroup>
          </div>

          {/* Categoría */}
          <div className="space-y-2">
            <Label>Categoría</Label>
            <Select value={categoryId} onValueChange={setCategoryId}>
              <SelectTrigger>
                <SelectValue placeholder="Selecciona categoría..." />
              </SelectTrigger>
              <SelectContent>
                {filteredCategories.length === 0 ? (
                  <SelectItem value="__none__" disabled>
                    Sin categorías para "{kind}" — créalas en Categorías
                  </SelectItem>
                ) : (
                  filteredCategories.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>

          {/* Monto */}
          <div className="space-y-2">
            <Label htmlFor="ef-amount">Monto (MXN)</Label>
            <Input
              id="ef-amount"
              type="number"
              min="0.01"
              step="0.01"
              placeholder="0.00"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </div>

          {/* Fecha */}
          <div className="space-y-2">
            <Label htmlFor="ef-date">Fecha</Label>
            <Input
              id="ef-date"
              type="date"
              value={incurredAt}
              onChange={(e) => setIncurredAt(e.target.value)}
            />
          </div>

          {/* Descripción */}
          <div className="space-y-2">
            <Label htmlFor="ef-desc">Descripción (opcional)</Label>
            <Textarea
              id="ef-desc"
              placeholder="Agrega una nota..."
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createExpense.isPending}>
              {createExpense.isPending ? "Guardando…" : "Guardar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
