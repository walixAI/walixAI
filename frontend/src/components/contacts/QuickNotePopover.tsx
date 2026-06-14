import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ContactAvatar } from "@/components/ui/ContactAvatar";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { createActivity } from "@/lib/queries/activities";
import type { ContactRow } from "@/lib/queries/contacts";

const MAX_CHARS = 500;
const MIN_CHARS = 2;

// ── Shared form content ───────────────────────────────────────────────────────

interface QuickNoteFormProps {
  contact: ContactRow;
  onClose: () => void;
  onSuccess: () => void;
}

function QuickNoteForm({ contact, onClose, onSuccess }: QuickNoteFormProps) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const fullName =
    [contact.name, contact.lastName].filter(Boolean).join(" ") || "Sin nombre";

  const mutation = useMutation({
    mutationFn: () =>
      createActivity(contact.id, { activityType: "note", body: text.trim() }),
    onMutate: () => {
      toast.success("Nota guardada", { duration: 3000, position: "bottom-right" });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contacts"] });
      onSuccess();
    },
    onError: () => {
      toast.error("No se pudo guardar la nota", {
        duration: 3000,
        position: "bottom-right",
      });
    },
  });

  const requestClose = () => {
    if (text.trim().length > 0) {
      setConfirmDiscard(true);
    } else {
      onClose();
    }
  };

  return (
    <>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <ContactAvatar
            id={contact.id}
            name={contact.name}
            lastName={contact.lastName}
            avatarUrl={null}
            size="sm"
          />
          <span className="text-sm font-medium truncate">{fullName}</span>
        </div>

        <div className="relative">
          <Textarea
            autoFocus
            placeholder="Escribe una nota..."
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
            className="resize-none min-h-[100px] pb-6 text-sm"
            onKeyDown={(e) => {
              if (e.key === "Escape") requestClose();
            }}
          />
          <span
            className={`absolute bottom-2 right-2 text-[10px] tabular-nums pointer-events-none
              ${text.length >= MAX_CHARS ? "text-destructive" : "text-muted-foreground"}`}
          >
            {text.length}/{MAX_CHARS}
          </span>
        </div>

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={requestClose}
            disabled={mutation.isPending}
          >
            Cancelar
          </Button>
          <Button
            size="sm"
            onClick={() => mutation.mutate()}
            disabled={text.trim().length < MIN_CHARS || mutation.isPending}
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                Guardando…
              </>
            ) : (
              "Guardar nota"
            )}
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDiscard}
        title="¿Descartar nota?"
        description="Perderás el texto escrito."
        confirmLabel="Descartar"
        cancelLabel="Seguir editando"
        destructive
        onConfirm={() => {
          setConfirmDiscard(false);
          onClose();
        }}
        onCancel={() => setConfirmDiscard(false)}
      />
    </>
  );
}

// ── Public component ──────────────────────────────────────────────────────────

interface QuickNotePopoverProps {
  contact: ContactRow;
  children: React.ReactNode;
}

export function QuickNotePopover({ contact, children }: QuickNotePopoverProps) {
  const [open, setOpen] = useState(false);
  const isMobile = typeof window !== "undefined" && window.innerWidth < 768;

  if (isMobile) {
    return (
      <>
        <span
          role="button"
          tabIndex={0}
          onClick={(e) => {
            e.stopPropagation();
            setOpen(true);
          }}
          onKeyDown={(e) => e.key === "Enter" && setOpen(true)}
        >
          {children}
        </span>
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent side="bottom">
            <SheetHeader className="mb-3">
              <SheetTitle>Nota rápida</SheetTitle>
            </SheetHeader>
            <QuickNoteForm
              contact={contact}
              onClose={() => setOpen(false)}
              onSuccess={() => setOpen(false)}
            />
          </SheetContent>
        </Sheet>
      </>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild onClick={(e) => e.stopPropagation()}>
        {children}
      </PopoverTrigger>
      <PopoverContent
        className="w-80 p-4"
        align="end"
        side="left"
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <QuickNoteForm
          contact={contact}
          onClose={() => setOpen(false)}
          onSuccess={() => setOpen(false)}
        />
      </PopoverContent>
    </Popover>
  );
}
