import { useState, useRef, useEffect } from "react";
import { Pencil, Check, X } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Option {
  value: string;
  label: string;
}

interface EditFieldPopoverProps {
  value: string;
  onSave: (newValue: string) => Promise<void> | void;
  fieldType?: "text" | "select" | "date";
  options?: Option[];
  required?: boolean;
  placeholder?: string;
  displayNode?: React.ReactNode;
  className?: string;
  fieldName?: string;
}

export function EditFieldPopover({
  value,
  onSave,
  fieldType = "text",
  options = [],
  required = false,
  placeholder,
  displayNode,
  className,
  fieldName,
}: EditFieldPopoverProps) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setDraft(value);
      setError(null);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open, value]);

  const handleSave = async () => {
    if (required && !draft.trim()) {
      setError("Este campo no puede estar vacío.");
      return;
    }
    if (draft === value) {
      setOpen(false);
      return;
    }
    setSaving(true);
    try {
      await onSave(draft);
      setOpen(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setSaving(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") { e.preventDefault(); handleSave(); }
    if (e.key === "Escape") setOpen(false);
  };

  const currentLabel =
    fieldType === "select"
      ? (options.find((o) => o.value === value)?.label ?? value)
      : value;

  return (
    <Popover open={open} onOpenChange={(o) => { if (!o) setOpen(false); }}>
      <PopoverTrigger asChild>
        <div
          data-testid={fieldName ? `field-${fieldName}` : undefined}
          className={`group flex items-center gap-1 cursor-pointer min-h-[20px] rounded px-1 -mx-1 hover:bg-muted/60 transition-colors ${className ?? ""}`}
          onClick={() => setOpen(true)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter") setOpen(true); }}
        >
          {displayNode ?? (
            <span className="text-sm text-foreground truncate flex-1">
              {currentLabel || <span className="text-muted-foreground italic">—</span>}
            </span>
          )}
          <Pencil
            data-testid={fieldName ? `edit-icon-${fieldName}` : undefined}
            className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 shrink-0 transition-opacity"
          />
        </div>
      </PopoverTrigger>

      <PopoverContent data-testid="edit-popover" className="w-64 p-3 space-y-2" align="start">
        {fieldType === "text" && (
          <Input
            data-testid="edit-input"
            ref={inputRef}
            value={draft}
            onChange={(e) => { setDraft(e.target.value); setError(null); }}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            className={`h-8 text-sm ${error ? "border-destructive" : ""}`}
          />
        )}

        {fieldType === "date" && (
          <Input
            data-testid="edit-input"
            ref={inputRef}
            type="date"
            value={draft}
            onChange={(e) => { setDraft(e.target.value); setError(null); }}
            onKeyDown={handleKeyDown}
            className={`h-8 text-sm ${error ? "border-destructive" : ""}`}
          />
        )}

        {fieldType === "select" && (
          <Select value={draft} onValueChange={(v) => { setDraft(v); setError(null); }}>
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {error && <p data-testid="edit-error" className="text-xs text-destructive">{error}</p>}

        <div className="flex gap-1.5 justify-end">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={() => setOpen(false)}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
          <Button
            data-testid="save-edit-btn"
            type="button"
            size="sm"
            className="h-7 px-2"
            onClick={handleSave}
            disabled={saving}
          >
            <Check className="h-3.5 w-3.5" />
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
