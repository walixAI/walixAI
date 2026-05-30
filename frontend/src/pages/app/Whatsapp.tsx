import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageCircle, ChevronLeft } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useIsMobile } from "@/hooks/use-mobile";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/walix/EmptyState";
import { EmptyIllustration } from "@/components/walix/empty/EmptyIllustration";
import { ConversationList } from "@/components/whatsapp/ConversationList";
import { ChatHeader } from "@/components/whatsapp/ChatHeader";
import { MessageList } from "@/components/whatsapp/MessageList";
import { Composer } from "@/components/whatsapp/Composer";
import { ContactSidePanel } from "@/components/whatsapp/ContactSidePanel";

export default function Whatsapp() {
  const isMobile = useIsMobile();
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();

  const [activeLeadId, setActiveLeadId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);

  // Fetch all leads
  const { data: leadsData, isLoading: leadsLoading } = useQuery({
    queryKey: ["leads", "whatsapp"],
    queryFn: () => api.listLeads({ all: true }),
    refetchInterval: 5_000,
  });

  const leads = leadsData?.items ?? [];

  // Open by deep link: ?leadId=...
  useEffect(() => {
    const leadParam = searchParams.get("leadId");
    if (leadParam) {
      setActiveLeadId(leadParam);
      const next = new URLSearchParams(searchParams);
      next.delete("leadId");
      setSearchParams(next, { replace: true });
      return;
    }
    if (!activeLeadId && leads.length) {
      setActiveLeadId(leads[0].id);
    }
  }, [leads, searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch active lead detail
  const { data: activeLead } = useQuery({
    queryKey: ["lead", activeLeadId],
    queryFn: () => api.getLead(activeLeadId!),
    enabled: !!activeLeadId,
  });

  // Fetch conversation
  const { data: conversation, isLoading: convLoading } = useQuery({
    queryKey: ["conversation", activeLeadId],
    queryFn: () => api.getConversation(activeLeadId!),
    enabled: !!activeLeadId,
    refetchInterval: 5_000,
  });

  const messages = conversation?.messages ?? [];

  // Fetch assignees for active lead
  const { data: assignees = [] } = useQuery({
    queryKey: ["assignees", activeLeadId],
    queryFn: () => api.getAssignees(activeLeadId!),
    enabled: !!activeLeadId,
  });

  // Send message
  const sendMutation = useMutation({
    mutationFn: (text: string) => api.sendMessage(activeLeadId!, text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["conversation", activeLeadId] });
    },
    onError: (e: any) => {
      toast.error("Error al enviar", { description: e?.message ?? "Intenta de nuevo" });
    },
  });

  // Handoff
  const handoffMutation = useMutation({
    mutationFn: () => api.handoff(activeLeadId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", activeLeadId] });
      qc.invalidateQueries({ queryKey: ["conversation", activeLeadId] });
      qc.invalidateQueries({ queryKey: ["leads", "whatsapp"] });
      toast.success("Control tomado — modo humano activo");
    },
    onError: (e: any) => {
      toast.error("Error", { description: e?.message });
    },
  });

  // Return to bot
  const returnToBotMutation = useMutation({
    mutationFn: () => api.returnToBot(activeLeadId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", activeLeadId] });
      qc.invalidateQueries({ queryKey: ["conversation", activeLeadId] });
      qc.invalidateQueries({ queryKey: ["leads", "whatsapp"] });
      toast.success("Devuelto al bot");
    },
    onError: (e: any) => {
      toast.error("Error", { description: e?.message });
    },
  });

  // Assign
  const assignMutation = useMutation({
    mutationFn: (userId: string) => api.assignLead(activeLeadId!, userId),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ["lead", activeLeadId] });
      qc.invalidateQueries({ queryKey: ["leads", "whatsapp"] });
      toast.success("Asignado a " + (updated.assigned_to_name ?? "usuario"));
    },
    onError: (e: any) => {
      toast.error("Error al asignar", { description: e?.message });
    },
  });

  const activeLead$ = useMemo(
    () => leads.find((l) => l.id === activeLeadId) ?? null,
    [leads, activeLeadId]
  );

  const loadingAction =
    handoffMutation.isPending ||
    returnToBotMutation.isPending ||
    assignMutation.isPending;

  // Mobile layout
  const showList = !isMobile || !activeLeadId;
  const showChat = !isMobile || !!activeLeadId;

  return (
    <div className="-m-4 md:-mx-6 md:-my-6 h-[calc(100vh-4rem)] flex bg-background overflow-hidden">
      {!leadsLoading && leads.length === 0 ? (
        <div className="flex-1 flex items-center justify-center p-6">
          <EmptyState
            illustration={<EmptyIllustration variant="whatsapp" />}
            title="Conecta tu WhatsApp Business"
            description="Cuando lleguen mensajes de tus leads apareceran aqui."
          />
        </div>
      ) : (
        <>
          {showList && (
            <ConversationList
              leads={leads}
              activeId={activeLeadId}
              onSelect={(id) => setActiveLeadId(id)}
              loading={leadsLoading}
            />
          )}

          {showChat && (
            <main className="flex-1 flex min-w-0">
              <div className="flex-1 flex flex-col min-w-0">
                {!activeLead$ && !activeLeadId && (
                  <div className="flex-1 flex flex-col items-center justify-center text-center p-8 text-muted-foreground">
                    <div className="h-16 w-16 rounded-full bg-success/10 flex items-center justify-center mb-3">
                      <MessageCircle className="h-8 w-8 text-success" />
                    </div>
                    <h3 className="font-semibold text-foreground">Selecciona un lead</h3>
                    <p className="text-sm mt-1 max-w-xs">
                      Elige un lead de la lista para ver la conversacion.
                    </p>
                  </div>
                )}

                {activeLeadId && (
                  <>
                    {isMobile && (
                      <div className="px-2 py-1 border-b border-border bg-card">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setActiveLeadId(null)}
                          className="h-8 text-xs"
                        >
                          <ChevronLeft className="h-4 w-4 mr-1" />
                          Leads
                        </Button>
                      </div>
                    )}

                    {activeLead && (
                      <ChatHeader
                        lead={activeLead}
                        conversation={conversation ?? null}
                        panelOpen={panelOpen}
                        onTogglePanel={() => setPanelOpen((v) => !v)}
                        onHandoff={() => handoffMutation.mutate()}
                        onReturnToBot={() => returnToBotMutation.mutate()}
                        onAssign={(userId) => assignMutation.mutate(userId)}
                        assignees={assignees}
                        loadingAction={loadingAction}
                      />
                    )}

                    <MessageList messages={messages} loading={convLoading} />

                    <Composer
                      onSend={(text) => sendMutation.mutate(text)}
                      sending={sendMutation.isPending}
                    />
                  </>
                )}
              </div>

              {activeLead && panelOpen && !isMobile && (
                <ContactSidePanel lead={activeLead} />
              )}
            </main>
          )}
        </>
      )}
    </div>
  );
}
