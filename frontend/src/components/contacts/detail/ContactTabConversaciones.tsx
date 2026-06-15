import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { MessageCircle, ExternalLink, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { ContactRow } from "@/lib/queries/contacts";
import { useTenantLabels } from "@/hooks/useTenantLabels";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface ContactTabConversacionesProps {
  contact: ContactRow;
}

export function ContactTabConversaciones({ contact }: ContactTabConversacionesProps) {
  const navigate = useNavigate();
  const contactId = contact.id;
  const { entity } = useTenantLabels();

  const { data: conversation, isLoading } = useQuery({
    queryKey: ["conversation", contactId],
    queryFn: () => api.getConversation(contactId),
    enabled: Boolean(contactId),
    staleTime: 30_000,
  });

  if (!contact.phone) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
        <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center mb-3">
          <MessageCircle className="h-6 w-6 text-muted-foreground" />
        </div>
        <p className="text-sm font-medium">Sin número de teléfono</p>
        <p className="text-xs text-muted-foreground mt-1 max-w-[260px]">
          Agrega un número de teléfono para iniciar conversaciones por WhatsApp
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-border p-3 space-y-2">
            <div className="flex items-center justify-between">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        ))}
      </div>
    );
  }

  const hasMessages = conversation && (conversation.messages ?? []).length > 0;

  if (!hasMessages) {
    return (
      <div data-testid="conversations-list" className="space-y-4">
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center mb-3">
            <MessageCircle className="h-6 w-6 text-muted-foreground" />
          </div>
          <p className="text-sm font-medium">Sin conversaciones</p>
          <p className="text-xs text-muted-foreground mt-1">Este {entity.toLowerCase()} no tiene hilos de WhatsApp.</p>
        </div>
        <Button
          variant="outline"
          className="w-full gap-2"
          onClick={() => navigate(`/whatsapp?phone=${contact.phone}`)}
        >
          <Plus className="h-4 w-4" />
          Iniciar conversación
        </Button>
      </div>
    );
  }

  const messages = conversation.messages ?? [];
  const firstMessage = messages[messages.length - 1];
  const lastMessage = messages[0];

  return (
    <div data-testid="conversations-list" className="space-y-4">
      <Button
        variant="outline"
        size="sm"
        className="gap-2"
        onClick={() => navigate(`/whatsapp?phone=${contact.phone}`)}
      >
        <Plus className="h-3.5 w-3.5" />
        Iniciar conversación
      </Button>

      {/* Single conversation thread */}
      <button
        type="button"
        className="w-full text-left rounded-xl border border-border bg-card p-3 space-y-2 hover:bg-muted/40 transition-colors"
        onClick={() => {
          if (conversation?.conversation_id) {
            navigate(`/whatsapp?conversation=${conversation.conversation_id}`);
          }
        }}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">
            {lastMessage ? formatDate(lastMessage.created_at) : "—"}
          </span>
          <span
            className={cn(
              "text-[10px] font-medium px-2 py-0.5 rounded-full border",
              conversation?.status === "active"
                ? "bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-300"
                : "bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-400",
            )}
          >
            {conversation?.status === "active" ? "Abierto" : "Cerrado"}
          </span>
        </div>

        <p className="text-sm leading-snug line-clamp-2 text-foreground/90">
          {firstMessage?.content?.slice(0, 80) ?? "Sin mensajes"}
          {(firstMessage?.content?.length ?? 0) > 80 ? "…" : ""}
        </p>

        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
          <span>{messages.length} mensaje{messages.length !== 1 ? "s" : ""}</span>
          <span className="flex items-center gap-0.5">
            Ver hilo <ExternalLink className="h-3 w-3 ml-0.5" />
          </span>
        </div>
      </button>
    </div>
  );
}
