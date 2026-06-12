import { useState } from "react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ContactAvatar } from "@/components/ui/ContactAvatar";
import { ContactStatusBadge, STATUS_CONFIG } from "@/components/ui/ContactStatusBadge";
import { TagSelect } from "@/components/ui/TagSelect";
import { EditFieldPopover } from "./EditFieldPopover";
import type { ContactRow, LeadStatus, TagRow } from "@/lib/queries/contacts";
import type { TeamMemberOut } from "@/lib/api";

const STATUS_OPTIONS: { value: string; label: string }[] = Object.entries(STATUS_CONFIG).map(
  ([value, { label }]) => ({ value, label }),
);

const SOURCE_OPTIONS = [
  { value: "whatsapp_inbound", label: "WhatsApp" },
  { value: "web_form",         label: "Formulario web" },
  { value: "referral",         label: "Referido" },
  { value: "manual",           label: "Manual" },
];

interface ContactLeftPanelProps {
  contact: ContactRow;
  team: TeamMemberOut[];
  onUpdate: (partial: Partial<ContactRow>) => Promise<void>;
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">{label}</p>
      {children}
    </div>
  );
}

function ReadonlyField({ value }: { value: string }) {
  return <p className="text-sm text-foreground truncate px-1 py-0.5">{value || "—"}</p>;
}

export function ContactLeftPanel({ contact, team, onUpdate }: ContactLeftPanelProps) {
  const fullName = [contact.name, contact.lastName].filter(Boolean).join(" ") || "Sin nombre";

  // Tags popover state
  const [tagsOpen, setTagsOpen] = useState(false);
  const [draftTags, setDraftTags] = useState<TagRow[]>(contact.tags);

  // Assigned user popover state
  const [assignedOpen, setAssignedOpen] = useState(false);

  const teamOptions = team.map((m) => ({ value: m.id, label: m.name }));

  const handleSaveTags = async () => {
    await onUpdate({ tags: draftTags });
    setTagsOpen(false);
  };

  return (
    <div className="space-y-4 p-4">
      {/* Avatar + name */}
      <div className="flex flex-col items-center gap-2 text-center">
        <ContactAvatar
          id={contact.id}
          name={contact.name}
          lastName={contact.lastName}
          size="lg"
        />
        <div>
          <p className="font-semibold">{fullName}</p>
          {contact.company && (
            <p className="text-xs text-muted-foreground">{contact.company}</p>
          )}
        </div>
      </div>

      <div className="border-t border-border pt-3 space-y-3">
        {/* Name */}
        <FieldRow label="Nombre">
          <EditFieldPopover
            fieldName="name"
            value={contact.name ?? ""}
            onSave={(v) => onUpdate({ name: v || null })}
            required={false}
            placeholder="Juan"
          />
        </FieldRow>

        {/* Last name */}
        <FieldRow label="Apellido">
          <EditFieldPopover
            value={contact.lastName ?? ""}
            onSave={(v) => onUpdate({ lastName: v || null })}
            placeholder="García"
          />
        </FieldRow>

        {/* Phone — readonly (primary key) */}
        <FieldRow label="Teléfono">
          <ReadonlyField value={contact.phone ?? "—"} />
        </FieldRow>

        {/* Email — not in backend yet */}
        <FieldRow label="Email">
          <ReadonlyField value="—" />
        </FieldRow>

        {/* Company */}
        <FieldRow label="Empresa">
          <EditFieldPopover
            fieldName="company"
            value={contact.company ?? ""}
            onSave={(v) => onUpdate({ company: v || null })}
            placeholder="ACME S.A."
          />
        </FieldRow>

        {/* Status */}
        <FieldRow label="Estado">
          <EditFieldPopover
            value={contact.status}
            fieldType="select"
            options={STATUS_OPTIONS}
            onSave={(v) => onUpdate({ status: v as LeadStatus })}
            displayNode={<ContactStatusBadge status={contact.status} />}
          />
        </FieldRow>

        {/* Source */}
        <FieldRow label="Fuente">
          <EditFieldPopover
            value={contact.prospectionSource}
            fieldType="select"
            options={SOURCE_OPTIONS}
            onSave={(v) => onUpdate({ prospectionSource: v })}
          />
        </FieldRow>

        {/* Tags */}
        <FieldRow label="Etiquetas">
          <Popover
            open={tagsOpen}
            onOpenChange={(o) => {
              if (o) setDraftTags(contact.tags);
              setTagsOpen(o);
            }}
          >
            <PopoverTrigger asChild>
              <div className="group flex items-start gap-1 cursor-pointer rounded px-1 -mx-1 hover:bg-muted/60 min-h-[24px] py-0.5">
                <div className="flex-1 flex flex-wrap gap-1">
                  {contact.tags.length > 0 ? (
                    contact.tags.map((t) => (
                      <span
                        key={t.id}
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border"
                        style={{
                          backgroundColor: `${t.color ?? "#6366f1"}20`,
                          borderColor: `${t.color ?? "#6366f1"}60`,
                          color: t.color ?? "#6366f1",
                        }}
                      >
                        {t.name}
                      </span>
                    ))
                  ) : (
                    <span className="text-sm text-muted-foreground italic">Sin etiquetas</span>
                  )}
                </div>
                <Pencil className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 shrink-0 mt-0.5" />
              </div>
            </PopoverTrigger>
            <PopoverContent className="w-64 p-3 space-y-3" align="start">
              <p className="text-xs font-medium">Editar etiquetas</p>
              <TagSelect value={draftTags} onChange={setDraftTags} />
              <div className="flex gap-1.5 justify-end">
                <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setTagsOpen(false)}>
                  Cancelar
                </Button>
                <Button size="sm" className="h-7 text-xs" onClick={handleSaveTags}>
                  Guardar
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        </FieldRow>

        {/* Assigned user */}
        <FieldRow label="Vendedor">
          <EditFieldPopover
            value={contact.assignedUser?.id ?? ""}
            fieldType="select"
            options={teamOptions}
            onSave={(id) => {
              const member = team.find((m) => m.id === id);
              onUpdate({
                assignedUser: member
                  ? { id: member.id, name: member.name, avatarUrl: null }
                  : null,
              });
            }}
            displayNode={
              contact.assignedUser ? (
                <span className="text-sm text-foreground">{contact.assignedUser.name}</span>
              ) : (
                <span className="text-sm text-muted-foreground italic">Sin asignar</span>
              )
            }
          />
        </FieldRow>

        {/* Created at — readonly */}
        <FieldRow label="Creado">
          <ReadonlyField
            value={new Date(contact.createdAt).toLocaleDateString("es-MX", {
              day: "2-digit",
              month: "short",
              year: "numeric",
            })}
          />
        </FieldRow>
      </div>
    </div>
  );
}
