import { useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/lib/api";
import {
  getContact,
  updateContact,
  deleteContact,
  type ContactRow,
} from "@/lib/queries/contacts";
import { getActivities } from "@/lib/queries/activities";
import { ContactDetailLayout } from "@/components/contacts/detail/ContactDetailLayout";
import { ContactLeftPanel } from "@/components/contacts/detail/ContactLeftPanel";
import { ContactRightPanel } from "@/components/contacts/detail/ContactRightPanel";
import { ContactTabs } from "@/components/contacts/detail/ContactTabs";
import { ContactDetailSkeleton } from "@/components/ui/ContactDetailSkeleton";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ContactAvatar } from "@/components/ui/ContactAvatar";
import { ContactStatusBadge } from "@/components/ui/ContactStatusBadge";
import { useTenantLabels } from "@/hooks/useTenantLabels";

export default function ContactDetailPage() {
  const { id: contactId = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const { entity, entities } = useTenantLabels();

  const [activeTab, setActiveTab] = useState("resumen");
  const [deleteOpen, setDeleteOpen] = useState(false);

  // ── Data ─────────────────────────────────────────────────────────────────────

  const { data: contact, isLoading: contactLoading } = useQuery({
    queryKey: ["contact", contactId],
    queryFn: () => getContact(contactId),
    enabled: Boolean(contactId),
    staleTime: 30_000,
  });

  const branchId = user?.branch_id ?? "";
  const { data: team = [] } = useQuery({
    queryKey: ["team", branchId],
    queryFn: () => api.getTeam(branchId),
    enabled: Boolean(branchId),
    staleTime: 5 * 60_000,
  });

  const activitiesQueryKey = ["activities", contactId, 1];
  const { data: activitiesData, isLoading: activitiesLoading } = useQuery({
    queryKey: activitiesQueryKey,
    queryFn: () => getActivities(contactId, { page: 1 }),
    enabled: Boolean(contactId),
    staleTime: 30_000,
  });

  // ── Mutations ─────────────────────────────────────────────────────────────────

  const updateMutation = useMutation({
    mutationFn: (partial: Partial<ContactRow>) => updateContact(contactId, partial),
    onSuccess: (updated) => {
      qc.setQueryData(["contact", contactId], updated);
      qc.invalidateQueries({ queryKey: ["contacts"] });
      toast.success("Guardado");
    },
    onError: (e: Error) => toast.error("Error al guardar", { description: e.message }),
  });

  const handleUpdate = useCallback(
    async (partial: Partial<ContactRow>) => {
      await updateMutation.mutateAsync(partial);
    },
    [updateMutation],
  );

  const deleteMutation = useMutation({
    mutationFn: () => deleteContact(contactId),
    onSuccess: () => {
      toast.success(`${entity} eliminado`);
      qc.invalidateQueries({ queryKey: ["contacts"] });
      navigate("/contacts");
    },
    onError: (e: Error) => toast.error("Error al eliminar", { description: e.message }),
  });

  // ── Loading / error ───────────────────────────────────────────────────────────

  if (contactLoading) {
    return (
      <div className="flex flex-col h-full overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <Link to="/contacts" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
            <ArrowLeft className="h-3.5 w-3.5" />
            {entities}
          </Link>
        </div>
        <ContactDetailSkeleton />
      </div>
    );
  }

  if (!contact) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <p className="text-muted-foreground">{entity} no encontrado.</p>
        <Button variant="outline" asChild>
          <Link to="/contacts">← Volver a {entities}</Link>
        </Button>
      </div>
    );
  }

  const fullName = [contact.name, contact.lastName].filter(Boolean).join(" ") || "Sin nombre";

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Topbar */}
      <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-border bg-background shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            to="/contacts"
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground shrink-0"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            {entities}
          </Link>
          <span className="text-muted-foreground">/</span>
          <div className="flex items-center gap-2 min-w-0">
            <ContactAvatar
              id={contact.id}
              name={contact.name}
              lastName={contact.lastName}
              size="sm"
            />
            <span className="text-sm font-medium truncate">{fullName}</span>
            <ContactStatusBadge status={contact.status} />
          </div>
        </div>

        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-destructive hover:text-destructive hover:bg-destructive/10"
          onClick={() => setDeleteOpen(true)}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* 3-column layout */}
      <div className="flex-1 overflow-hidden">
        <ContactDetailLayout
          leftPanel={
            <ContactLeftPanel
              contact={contact}
              team={team}
              onUpdate={handleUpdate}
            />
          }
          center={
            <ContactTabs
              contact={contact}
              recentActivities={activitiesData?.items ?? []}
              activitiesTotal={activitiesData?.total ?? 0}
              activitiesLoading={activitiesLoading}
              activitiesQueryKey={activitiesQueryKey}
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />
          }
          rightPanel={<ContactRightPanel contactId={contactId} />}
        />
      </div>

      {/* Delete confirm */}
      <ConfirmDialog
        open={deleteOpen}
        title={`Eliminar a ${fullName}`}
        description="Esta acción eliminará permanentemente el contacto y no podrá deshacerse."
        confirmLabel="Eliminar"
        destructive
        onConfirm={() => { setDeleteOpen(false); deleteMutation.mutate(); }}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  );
}
