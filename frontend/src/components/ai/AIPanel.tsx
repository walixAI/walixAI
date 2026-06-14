import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Building2, Phone, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { AIActionData, ContactInfo } from "@/lib/api";
import { useAIBarStore } from "@/stores/aiBarStore";
import { ContactStatusBadge } from "@/components/ui/ContactStatusBadge";
import { ContactAvatar } from "@/components/ui/ContactAvatar";
import type { LeadStatus } from "@/lib/queries/contacts";
import {
  Sheet,
  SheetContent,
  SheetClose,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentSuggestionsPanel } from "@/components/agents/AgentSuggestionsPanel";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString("es-MX", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

const NAVIGATE_KEYWORDS = ["ver ", "ir a ", "abrir ", "navegar", "pipeline", "dashboard", "whatsapp"];
const CONFIRM_KEYWORDS = ["eliminar", "borrar", "cancelar", "revocar", "desactivar", "archivar"];

type ActionKind = "navigate" | "confirm_action" | "send";

function classifyAction(label: string): ActionKind {
  const lower = label.toLowerCase();
  if (CONFIRM_KEYWORDS.some((kw) => lower.includes(kw))) return "confirm_action";
  if (NAVIGATE_KEYWORDS.some((kw) => lower.includes(kw))) return "navigate";
  return "send";
}

const SCREEN_ROUTES: Record<string, string> = {
  pipeline: "/pipeline",
  dashboard: "/dashboard",
  whatsapp: "/whatsapp",
  leads: "/whatsapp",
  contacts: "/contacts",
  settings: "/settings",
};

function resolveNavigatePath(label: string): string {
  const lower = label.toLowerCase();
  for (const [kw, path] of Object.entries(SCREEN_ROUTES)) {
    if (lower.includes(kw)) return path;
  }
  // UUID pattern → lead detail via whatsapp
  const uuid = label.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
  if (uuid) return `/whatsapp?lead=${uuid[0]}`;
  return "/dashboard";
}

// ── Contact action cards ──────────────────────────────────────────────────────

function ContactCard({ contact, onNavigate }: { contact: ContactInfo; onNavigate: (p: string) => void }) {
  const fullName = [contact.name, contact.lastName].filter(Boolean).join(" ") || "Sin nombre";
  return (
    <div className="rounded-xl border border-border bg-card/40 p-3 space-y-2 mt-2">
      <div className="flex items-center gap-2">
        <ContactAvatar id={contact.id} name={contact.name ?? null} lastName={contact.lastName ?? null} avatarUrl={null} size="sm" />
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">{fullName}</p>
          {contact.company && <p className="text-xs text-muted-foreground truncate">{contact.company}</p>}
        </div>
        {contact.status && (
          <div className="ml-auto shrink-0">
            <ContactStatusBadge status={contact.status as LeadStatus} />
          </div>
        )}
      </div>
      {contact.phone && (
        <p className="flex items-center gap-1 text-xs font-mono text-muted-foreground">
          <Phone className="h-3 w-3" />{contact.phone}
        </p>
      )}
      <button
        onClick={() => onNavigate(`/contacts/${contact.id}`)}
        className="w-full text-xs h-7 rounded-lg border border-border bg-background/50 hover:bg-background transition-colors"
      >
        Ver ficha
      </button>
    </div>
  );
}

function ContactListItem({ contact, onNavigate }: { contact: ContactInfo; onNavigate: (p: string) => void }) {
  const fullName = [contact.name, contact.lastName].filter(Boolean).join(" ") || "Sin nombre";
  return (
    <button
      onClick={() => onNavigate(`/contacts/${contact.id}`)}
      className="flex items-center gap-2 w-full rounded-lg px-2 py-1.5 hover:bg-muted/50 transition-colors text-left"
    >
      <ContactAvatar id={contact.id} name={contact.name ?? null} lastName={contact.lastName ?? null} avatarUrl={null} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium truncate">{fullName}</p>
        {contact.company && <p className="text-[11px] text-muted-foreground truncate">{contact.company}</p>}
      </div>
      {contact.status && <ContactStatusBadge status={contact.status as LeadStatus} />}
    </button>
  );
}

function ActionDataCard({
  data,
  onNavigate,
  onConfirmDelete,
  onCancelDelete,
}: {
  data: AIActionData;
  onNavigate: (p: string) => void;
  onConfirmDelete: (d: AIActionData) => void;
  onCancelDelete: () => void;
}) {
  if (data.action === "contact_created" && data.contact) {
    return <ContactCard contact={data.contact} onNavigate={onNavigate} />;
  }

  if (data.action === "contact_found" && data.contact) {
    return (
      <div className="mt-2 space-y-1">
        <ContactCard contact={data.contact} onNavigate={onNavigate} />
      </div>
    );
  }

  if (data.action === "contacts_found" && data.contacts) {
    return (
      <div className="mt-2 rounded-xl border border-border bg-card/40 p-2 space-y-0.5">
        {data.contacts.map((c) => (
          <ContactListItem key={c.id} contact={c} onNavigate={onNavigate} />
        ))}
        {data.total && data.total > (data.contacts.length) && (
          <button
            onClick={() => onNavigate("/contacts")}
            className="w-full text-xs text-primary hover:underline pt-1 pb-0.5"
          >
            Ver todos ({data.total})
          </button>
        )}
      </div>
    );
  }

  if (data.action === "activity_created") {
    return (
      <div className="mt-2 flex items-center gap-2 rounded-xl border border-border bg-card/40 px-3 py-2">
        <span className="text-base">{data.emoji ?? "📝"}</span>
        <p className="text-xs text-muted-foreground">{data.message}</p>
      </div>
    );
  }

  if (data.action === "requires_confirmation") {
    return (
      <div className="mt-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3 space-y-2.5">
        <p className="text-xs text-foreground">{data.message}</p>
        <div className="flex gap-2">
          <button
            onClick={() => onConfirmDelete(data)}
            className="flex-1 h-7 rounded-lg text-xs bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors"
          >
            Sí, archivar
          </button>
          <button
            onClick={onCancelDelete}
            className="flex-1 h-7 rounded-lg text-xs border border-border hover:bg-muted/50 transition-colors"
          >
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  if (data.action === "ambiguous") {
    return (
      <div className="mt-2 rounded-xl border border-amber-500/30 bg-amber-500/5 px-3 py-2">
        <p className="text-xs text-muted-foreground">{data.message}</p>
      </div>
    );
  }

  return null;
}

// ── Urgency border ────────────────────────────────────────────────────────────

const URGENCY_BORDER: Record<string, string> = {
  high: "border-destructive",
  medium: "border-warning",
  low: "border-primary",
};

// ── Suggested action chip ─────────────────────────────────────────────────────

function SuggestedChip({
  label,
  onNavigate,
  onConfirm,
  onSend,
}: {
  label: string;
  onNavigate: (path: string) => void;
  onConfirm: (label: string) => void;
  onSend: (label: string) => void;
}) {
  const kind = classifyAction(label);

  const handleClick = () => {
    if (kind === "navigate") onNavigate(resolveNavigatePath(label));
    else if (kind === "confirm_action") onConfirm(label);
    else onSend(label);
  };

  return (
    <button
      onClick={handleClick}
      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs
                 bg-primary/15 text-primary border border-primary/30
                 hover:bg-primary/25 transition-colors text-left"
    >
      {label}
    </button>
  );
}

// ── Context insight card ──────────────────────────────────────────────────────

function InsightCard({
  screen,
  branchId,
  onSend,
  onNavigate,
  onConfirm,
}: {
  screen: string;
  branchId?: string;
  onSend: (label: string) => void;
  onNavigate: (path: string) => void;
  onConfirm: (label: string) => void;
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai-insight", screen, branchId],
    queryFn: () => api.getContextInsight(screen, branchId),
    staleTime: 2 * 60 * 1_000,
    retry: false,
    enabled: Boolean(screen),
  });

  if (isError) return null;

  if (isLoading) {
    return (
      <div className="mx-4 mt-4 rounded-xl border border-primary/30 bg-primary/5 p-3 space-y-2">
        <Skeleton className="h-3 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
        <div className="flex gap-1.5 pt-1">
          <Skeleton className="h-6 w-20 rounded-full" />
          <Skeleton className="h-6 w-24 rounded-full" />
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div
      className={cn(
        "mx-4 mt-4 rounded-xl border bg-primary/5 p-3",
        URGENCY_BORDER[data.urgency] ?? "border-primary",
      )}
    >
      <div className="flex items-start gap-2">
        <span className="text-primary text-sm leading-none mt-0.5 shrink-0">✦</span>
        <p className="text-xs text-foreground leading-relaxed">{data.insight}</p>
      </div>
      {data.suggested_actions.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {data.suggested_actions.map((action, i) => (
            <SuggestedChip
              key={i}
              label={action}
              onNavigate={onNavigate}
              onConfirm={onConfirm}
              onSend={onSend}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Confirm dialog ────────────────────────────────────────────────────────────

function ConfirmActionDialog({
  label,
  open,
  onConfirm,
  onCancel,
}: {
  label: string;
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <AlertDialog open={open}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Confirmar acción</AlertDialogTitle>
          <AlertDialogDescription>
            ¿Deseas ejecutar: <strong>{label}</strong>?
            <br />
            Esta acción puede no ser reversible.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>Cancelar</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Confirmar</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function AIPanel() {
  const navigate = useNavigate();
  const { isOpen, isLoading, history, currentContext, setOpen, setDraftInput, setPendingCommand } =
    useAIBarStore();

  const bottomRef = useRef<HTMLDivElement>(null);
  const [confirmAction, setConfirmAction] = useState<string | null>(null);

  // Scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, isLoading]);

  // Context label: "Pipeline · Sucursal Monterrey"
  const contextLabel = [
    currentContext.screen,
    currentContext.branch_name as string | undefined,
  ]
    .filter(Boolean)
    .map((s) => (s as string).charAt(0).toUpperCase() + (s as string).slice(1))
    .join(" · ");

  const handleSend = (label: string) => {
    setDraftInput(label);
    // Bar picks up draftInput via useEffect and focuses itself
  };

  const handleNavigate = (path: string) => {
    setOpen(false);
    navigate(path);
  };

  const handleConfirmRequest = (label: string) => setConfirmAction(label);

  const handleConfirmExecute = () => {
    if (confirmAction) handleSend(confirmAction);
    setConfirmAction(null);
  };

  return (
    <>
      <Sheet
        open={isOpen}
        onOpenChange={(v) => {
          // Only allow closing via the Sheet mechanism (escape key etc.)
          if (!v) setOpen(false);
        }}
      >
        <SheetContent
          side="right"
          // 360px wide; no overlay-click dismiss; remove default padding
          className="dark p-0 w-full sm:max-w-[360px] flex flex-col gap-0
                     [&>button:first-of-type]:hidden"
          onInteractOutside={(e) => e.preventDefault()}
          onPointerDownOutside={(e) => e.preventDefault()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
            <div className="flex flex-col gap-0.5">
              <div className="flex items-center gap-2">
                <span className="text-primary text-sm leading-none">✦</span>
                <span className="text-sm font-semibold text-foreground">Walix AI</span>
              </div>
              {contextLabel && (
                <p className="text-[11px] text-muted-foreground pl-5">{contextLabel}</p>
              )}
            </div>
            <SheetClose asChild>
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground
                           hover:bg-muted transition-colors"
                aria-label="Cerrar panel"
              >
                <X className="h-4 w-4" />
              </button>
            </SheetClose>
          </div>

          {/* Context insight card — sticky below header */}
          {currentContext.screen && (
            <InsightCard
              screen={currentContext.screen}
              branchId={currentContext.branch_id}
              onSend={handleSend}
              onNavigate={handleNavigate}
              onConfirm={handleConfirmRequest}
            />
          )}

          {/* Agent suggestions — above message history */}
          <AgentSuggestionsPanel />

          {/* Messages */}
          <ScrollArea className="flex-1 px-4 py-4">
            {history.length === 0 && !isLoading && (
              <div className="flex flex-col items-center justify-center h-48 gap-3 text-center">
                <span className="text-primary text-4xl">✦</span>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Escribe una instrucción o pregunta.
                  <br />
                  Walix actúa directamente en tu CRM.
                </p>
              </div>
            )}

            <div className="space-y-5">
              {history.map((msg, i) => (
                <div
                  key={i}
                  className={cn(
                    "flex flex-col gap-1.5",
                    msg.role === "user" ? "items-end" : "items-start",
                  )}
                >
                  <div
                    className={cn(
                      "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-br-sm"
                        : "bg-muted text-foreground rounded-bl-sm",
                    )}
                  >
                    {msg.content}
                  </div>

                  <span className="text-[10px] text-muted-foreground px-1">
                    {formatTime(msg.timestamp)}
                  </span>

                  {/* Contact action cards */}
                  {msg.role === "assistant" && msg.action_data && (
                    <div className="max-w-[85%] w-full">
                      <ActionDataCard
                        data={msg.action_data}
                        onNavigate={handleNavigate}
                        onConfirmDelete={(d) =>
                          setPendingCommand({
                            message: "__confirm__",
                            displayText: "Confirmar archivado",
                            context: {
                              confirmation_action: {
                                type: "contact_delete",
                                confirmation_id: d.confirmationId,
                                contact_id: d.contactId,
                              },
                            },
                          })
                        }
                        onCancelDelete={() => {/* no-op — user cancelled */}}
                      />
                    </div>
                  )}

                  {/* Suggested actions below assistant messages */}
                  {msg.role === "assistant" &&
                    msg.suggested_actions &&
                    msg.suggested_actions.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 max-w-[85%]">
                        {msg.suggested_actions.map((action, j) => (
                          <SuggestedChip
                            key={j}
                            label={action}
                            onNavigate={handleNavigate}
                            onConfirm={handleConfirmRequest}
                            onSend={handleSend}
                          />
                        ))}
                      </div>
                    )}
                </div>
              ))}

              {/* Thinking indicator */}
              {isLoading && (
                <div className="flex items-start">
                  <div className="bg-muted rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm
                                  text-muted-foreground flex items-center gap-2">
                    <span className="text-primary animate-pulse text-base leading-none">✦</span>
                    Walix está pensando…
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          </ScrollArea>
        </SheetContent>
      </Sheet>

      {/* Confirm-action dialog rendered outside the Sheet to avoid z-index conflicts */}
      {confirmAction && (
        <ConfirmActionDialog
          label={confirmAction}
          open={Boolean(confirmAction)}
          onConfirm={handleConfirmExecute}
          onCancel={() => setConfirmAction(null)}
        />
      )}
    </>
  );
}
