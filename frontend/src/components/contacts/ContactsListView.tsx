import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/TableSkeleton";
import { ContactStatusBadge } from "@/components/ui/ContactStatusBadge";
import { ContactAvatar } from "@/components/ui/ContactAvatar";
import { TagChip } from "@/components/ui/TagChip";
import { LeadScoreBadge } from "@/components/leads/LeadScoreBadge";
import type { ContactListResponse } from "@/lib/queries/contacts";

const SOURCE_LABELS: Record<string, string> = {
  whatsapp_inbound: "WhatsApp",
  web_form:         "Web",
  referral:         "Referido",
  manual:           "Manual",
};

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const d = Math.floor(diff / 86_400_000);
  if (d === 0) return "Hoy";
  if (d === 1) return "Ayer";
  if (d < 30) return `hace ${d}d`;
  if (d < 365) return `hace ${Math.floor(d / 30)}m`;
  return `hace ${Math.floor(d / 365)}a`;
}

interface ContactsListViewProps {
  data: ContactListResponse | undefined;
  isLoading: boolean;
  page: number;
  onPageChange: (page: number) => void;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onToggleAll: (ids: string[]) => void;
}

export function ContactsListView({
  data,
  isLoading,
  page,
  onPageChange,
  selectedIds,
  onToggleSelect,
  onToggleAll,
}: ContactsListViewProps) {
  const navigate = useNavigate();
  const items = data?.items ?? [];
  const totalPages = data ? Math.ceil(data.total / data.pageSize) : 1;
  const allSelected = items.length > 0 && items.every((c) => selectedIds.has(c.id));

  if (isLoading) {
    return <TableSkeleton rows={10} columns={9} />;
  }

  if (!isLoading && items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <p className="text-muted-foreground text-sm">No se encontraron contactos.</p>
        <p className="text-muted-foreground text-xs mt-1">Cambia los filtros o crea un nuevo contacto.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="overflow-auto flex-1">
        <Table data-testid="contacts-table">
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <Checkbox
                  checked={allSelected}
                  onCheckedChange={() => onToggleAll(items.map((c) => c.id))}
                  aria-label="Seleccionar todos"
                />
              </TableHead>
              <TableHead>Contacto</TableHead>
              <TableHead>Empresa</TableHead>
              <TableHead>Teléfono</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Fuente</TableHead>
              <TableHead>Vendedor</TableHead>
              <TableHead>Última actividad</TableHead>
              <TableHead className="text-right">Score</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((contact) => {
              const fullName = [contact.name, contact.lastName].filter(Boolean).join(" ") || "Sin nombre";
              return (
                <TableRow
                  key={contact.id}
                  data-testid="contact-row"
                  className="cursor-pointer hover:bg-muted/40"
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest('[role="checkbox"]')) return;
                    navigate(`/contacts/${contact.id}`);
                  }}
                >
                  <TableCell
                    onClick={(e) => e.stopPropagation()}
                    className="w-10"
                  >
                    <Checkbox
                      checked={selectedIds.has(contact.id)}
                      onCheckedChange={() => onToggleSelect(contact.id)}
                      aria-label={`Seleccionar ${fullName}`}
                    />
                  </TableCell>

                  <TableCell>
                    <div className="flex items-center gap-2">
                      <ContactAvatar
                        id={contact.id}
                        name={contact.name}
                        lastName={contact.lastName}
                        avatarUrl={contact.assignedUser?.avatarUrl}
                        size="sm"
                      />
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate max-w-[160px]">{fullName}</p>
                        {contact.tags.length > 0 && (
                          <div className="flex gap-1 mt-0.5 flex-wrap">
                            {contact.tags.slice(0, 2).map((t) => (
                              <TagChip key={t.id} tag={t} />
                            ))}
                            {contact.tags.length > 2 && (
                              <span className="text-[10px] text-muted-foreground">+{contact.tags.length - 2}</span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </TableCell>

                  <TableCell className="text-sm text-muted-foreground truncate max-w-[120px]">
                    {contact.company ?? "—"}
                  </TableCell>

                  <TableCell className="text-sm font-mono text-muted-foreground">
                    {contact.phone ?? "—"}
                  </TableCell>

                  <TableCell>
                    <ContactStatusBadge status={contact.status} />
                  </TableCell>

                  <TableCell className="text-xs text-muted-foreground">
                    {SOURCE_LABELS[contact.prospectionSource] ?? contact.prospectionSource}
                  </TableCell>

                  <TableCell className="text-xs text-muted-foreground truncate max-w-[100px]">
                    {contact.assignedUser?.name ?? "—"}
                  </TableCell>

                  <TableCell className="text-xs text-muted-foreground">
                    {formatRelative(contact.lastActivityAt)}
                  </TableCell>

                  <TableCell className="text-right">
                    {contact.currentScore != null ? (
                      <LeadScoreBadge
                        score={contact.currentScore}
                        trend={contact.currentScoreTrend as "up" | "down" | "flat" | null}
                      />
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {data && data.total > data.pageSize && (
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-border shrink-0">
          <p className="text-xs text-muted-foreground">
            {data.total} contactos — página {page} de {totalPages}
          </p>
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
              className="h-7 px-2"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
              className="h-7 px-2"
            >
              Siguiente
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
