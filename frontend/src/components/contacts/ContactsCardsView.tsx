import { useNavigate } from "react-router-dom";
import { Eye, Pencil, Phone } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ListRowsSkeleton } from "@/components/ui/ListRowsSkeleton";
import { ContactStatusBadge } from "@/components/ui/ContactStatusBadge";
import { ContactAvatar } from "@/components/ui/ContactAvatar";
import { TagChip } from "@/components/ui/TagChip";
import { LeadScoreBadge } from "@/components/leads/LeadScoreBadge";
import type { ContactRow } from "@/lib/queries/contacts";

const SOURCE_LABELS: Record<string, string> = {
  whatsapp_inbound: "WhatsApp",
  web_form:         "Web",
  referral:         "Referido",
  manual:           "Manual",
};

interface ContactsCardsViewProps {
  contacts: ContactRow[];
  isLoading: boolean;
  onEdit?: (contact: ContactRow) => void;
}

export function ContactsCardsView({ contacts, isLoading, onEdit }: ContactsCardsViewProps) {
  const navigate = useNavigate();

  if (isLoading) {
    return <ListRowsSkeleton count={9} />;
  }

  if (contacts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <p className="text-muted-foreground text-sm">No se encontraron contactos.</p>
        <p className="text-muted-foreground text-xs mt-1">Cambia los filtros o crea un nuevo contacto.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {contacts.map((contact) => {
        const fullName = [contact.name, contact.lastName].filter(Boolean).join(" ") || "Sin nombre";
        return (
          <div
            key={contact.id}
            className="group relative rounded-xl border border-border bg-card p-4 space-y-3 hover:shadow-md transition-shadow"
          >
            {/* Hover overlay */}
            <div className="absolute inset-0 rounded-xl bg-background/60 backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2 z-10">
              <Button
                size="sm"
                onClick={() => navigate(`/contacts/${contact.id}`)}
                className="h-8"
              >
                <Eye className="h-3.5 w-3.5 mr-1" />
                Ver ficha
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onEdit?.(contact)}
                className="h-8"
              >
                <Pencil className="h-3.5 w-3.5 mr-1" />
                Editar
              </Button>
            </div>

            {/* Avatar + name */}
            <div className="flex items-center gap-3">
              <ContactAvatar
                id={contact.id}
                name={contact.name}
                lastName={contact.lastName}
                size="lg"
              />
              <div className="min-w-0 flex-1">
                <p className="font-semibold truncate">{fullName}</p>
                {contact.company && (
                  <p className="text-xs text-muted-foreground truncate">{contact.company}</p>
                )}
              </div>
              {contact.currentScore != null && (
                <LeadScoreBadge
                  score={contact.currentScore}
                  trend={contact.currentScoreTrend as "up" | "down" | "flat" | null}
                />
              )}
            </div>

            {/* Status + source */}
            <div className="flex items-center gap-2 flex-wrap">
              <ContactStatusBadge status={contact.status} />
              <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                {SOURCE_LABELS[contact.prospectionSource] ?? contact.prospectionSource}
              </span>
            </div>

            {/* Phone (click-to-call) */}
            {contact.phone && (
              <a
                href={`tel:${contact.phone}`}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <Phone className="h-3 w-3 shrink-0" />
                <span className="font-mono">{contact.phone}</span>
              </a>
            )}

            {/* Tags */}
            {contact.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {contact.tags.map((tag) => (
                  <TagChip key={tag.id} tag={tag} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
