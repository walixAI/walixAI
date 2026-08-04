import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageCircle, ChevronLeft } from "lucide-react";
import { api } from "@/lib/api";
import type { MessageOut } from "@/lib/api";
import { getServiceWindowFromMessages } from "@/lib/whatsapp/serviceWindow";
import { getGuidance } from "@/lib/whatsapp/guidance";
import { toast } from "sonner";
import { useIsMobile } from "@/hooks/use-mobile";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/walix/EmptyState";
import { EmptyIllustration } from "@/components/walix/empty/EmptyIllustration";
import { ConversationList } from "@/components/whatsapp/ConversationList";
import { ChatHeader } from "@/components/whatsapp/ChatHeader";
import { ConversationBanner } from "@/components/whatsapp/ConversationBanner";
import { MessageList, type PendingMsg } from "@/components/whatsapp/MessageList";
import { Composer } from "@/components/whatsapp/Composer";
import { ContactSidePanel } from "@/components/whatsapp/ContactSidePanel";

export default function Whatsapp() {
  const isMobile = useIsMobile();
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();

  const [activeLeadId, setActiveLeadId] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);

  // Reply composer state — controlled from here so we can preserve text on error
  const [draft, setDraft] = useState("");
  const [replyError, setReplyError] = useState<string | null>(null);
  const [pendingMessages, setPendingMessages] = useState<PendingMsg[]>([]);
  const [aiDraftActive, setAiDraftActive] = useState(false);
  const lastSuggestedDraft = useRef<string | null>(null);
  const pendingSuggestedDraft = useRef<string | undefined>(undefined);

  // Reset composer state when switching leads
  useEffect(() => {
    setDraft("");
    setReplyError(null);
    setPendingMessages([]);
    setAiDraftActive(false);
    lastSuggestedDraft.current = null;
  }, [activeLeadId]);

  // Fetch all leads — 5 s refresh for real-time inbox
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
    if (!activeLeadId && leads.length) setActiveLeadId(leads[0].id);
  }, [leads, searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  // Active lead detail
  const { data: activeLead } = useQuery({
    queryKey: ["lead", activeLeadId],
    queryFn: () => api.getLead(activeLeadId!),
    enabled: !!activeLeadId,
  });

  // Conversation — 5 s refresh so asistente sees new messages in real time
  const { data: conversation, isLoading: convLoading } = useQuery({
    queryKey: ["conversation", activeLeadId],
    queryFn: () => api.getConversation(activeLeadId!),
    enabled: !!activeLeadId,
    refetchInterval: 5_000,
  });

  const messages = conversation?.messages ?? [];
  const isHuman = conversation?.current_handler === "human";

  // When a server refresh arrives, drop any pending msg already included
  useEffect(() => {
    if (!messages.length) return;
    const serverIds = new Set(messages.map((m) => m.id));
    setPendingMessages((prev) => prev.filter((p) => !serverIds.has(p.id)));
  }, [messages]);

  // Assignees
  const { data: assignees = [] } = useQuery({
    queryKey: ["assignees", activeLeadId],
    queryFn: () => api.getAssignees(activeLeadId!),
    enabled: !!activeLeadId,
  });

  // Resolve handler display name from assignees list
  const handlerName = useMemo(() => {
    if (!conversation?.handler_user_id) return "Asistente";
    return assignees.find((a) => a.id === conversation.handler_user_id)?.name ?? "Asistente";
  }, [conversation?.handler_user_id, assignees]);

  // ── Mutations ──────────────────────────────────────────────────────────────

  const handoffMutation = useMutation({
    mutationFn: () => api.handoff(activeLeadId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", activeLeadId] });
      qc.invalidateQueries({ queryKey: ["conversation", activeLeadId] });
      qc.invalidateQueries({ queryKey: ["leads", "whatsapp"] });
      toast.success("Control tomado — modo humano activo");
    },
    onError: (e: Error) => toast.error("Error", { description: e.message }),
  });

  const returnToBotMutation = useMutation({
    mutationFn: () => api.returnToBot(activeLeadId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead", activeLeadId] });
      qc.invalidateQueries({ queryKey: ["conversation", activeLeadId] });
      qc.invalidateQueries({ queryKey: ["leads", "whatsapp"] });
      setDraft("");
      setReplyError(null);
      setPendingMessages([]);
      toast.success("Devuelto al bot");
    },
    onError: (e: Error) => toast.error("Error", { description: e.message }),
  });

  const assignMutation = useMutation({
    mutationFn: (userId: string) => api.assignLead(activeLeadId!, userId),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ["lead", activeLeadId] });
      qc.invalidateQueries({ queryKey: ["leads", "whatsapp"] });
      toast.success("Asignado a " + (updated.assigned_to_name ?? "usuario"));
    },
    onError: (e: Error) => toast.error("Error al asignar", { description: e.message }),
  });

  const replyMutation = useMutation({
    mutationFn: (text: string) => api.reply(activeLeadId!, text, pendingSuggestedDraft.current),
    onMutate: (text) => {
      // Optimistic message — temp id prefixed so we can identify it
      const tempId = `pending-${Date.now()}`;
      const optimistic: PendingMsg = {
        id: tempId,
        role: "assistant",
        content: text,
        tokens_used: null,
        latency_ms: null,
        created_at: new Date().toISOString(),
        sent_by_user_id: "pending",   // non-null → renders as human bubble
        _status: "sending",
      };
      setPendingMessages((prev) => [...prev, optimistic]);
      setReplyError(null);
      return { tempId };
    },
    onSuccess: (_data, _vars, ctx) => {
      setDraft("");
      // Remove the optimistic msg — the 5 s refresh will load the real one
      setPendingMessages((prev) => prev.filter((m) => m.id !== ctx?.tempId));
      qc.invalidateQueries({ queryKey: ["conversation", activeLeadId] });
    },
    onError: (e: Error, _vars, ctx) => {
      // Mark the optimistic message as errored; keep draft for re-send
      setPendingMessages((prev) =>
        prev.map((m) =>
          m.id === ctx?.tempId
            ? { ...m, _status: "error" as const, _errorText: e.message }
            : m
        )
      );
      setReplyError(e.message);
    },
  });

  const handleSend = () => {
    const text = draft.trim();
    if (!text || replyMutation.isPending) return;
    pendingSuggestedDraft.current = aiDraftActive ? (lastSuggestedDraft.current ?? undefined) : undefined;
    replyMutation.mutate(text);
  };

  const suggestMutation = useMutation({
    mutationFn: () => api.getSuggestReply(conversation!.conversation_id!),
  });

  const runAiSuggest = async () => {
    if (!conversation?.conversation_id) return;
    try {
      const result = await suggestMutation.mutateAsync();
      if (result.draft) {
        setDraft(result.draft);
        setAiDraftActive(true);
        lastSuggestedDraft.current = result.draft;
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error al generar el borrador";
      toast.error("No se pudo sugerir respuesta", { description: msg });
    }
  };

  const activeLead$ = useMemo(
    () => leads.find((l) => l.id === activeLeadId) ?? null,
    [leads, activeLeadId]
  );

  const serviceWindow = useMemo(
    () => getServiceWindowFromMessages(messages),
    [messages]
  );
  const guidance = useMemo(
    () => getGuidance(messages, serviceWindow),
    [messages, serviceWindow]
  );

  const loadingAction =
    handoffMutation.isPending || returnToBotMutation.isPending || assignMutation.isPending;

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

                    {/* Handoff status banner */}
                    {conversation && (
                      <ConversationBanner
                        currentHandler={conversation.current_handler}
                        handlerName={handlerName}
                        onHandoff={() => handoffMutation.mutate()}
                        onReturnToBot={() => returnToBotMutation.mutate()}
                        loading={loadingAction}
                      />
                    )}

                    <MessageList
                      messages={messages}
                      pendingMessages={pendingMessages}
                      loading={convLoading}
                    />

                    {/* Composer only visible when human has control */}
                    {isHuman && (
                      <Composer
                        value={draft}
                        onChange={(v) => {
                          setDraft(v);
                          if (replyError) setReplyError(null);
                        }}
                        onSend={handleSend}
                        sending={replyMutation.isPending}
                        sendError={replyError}
                        placeholder={`Escribe tu mensaje a ${activeLead?.name ?? activeLead?.wa_phone ?? "el lead"}...`}
                        onAiSuggest={runAiSuggest}
                        aiLoading={suggestMutation.isPending}
                        aiDraftActive={aiDraftActive}
                        onClearAiDraft={() => setAiDraftActive(false)}
                        serviceWindow={serviceWindow}
                        leadId={activeLeadId ?? undefined}
                        branchId={activeLead?.branch_id}
                      />
                    )}
                  </>
                )}
              </div>

              {activeLead && panelOpen && !isMobile && (
                <ContactSidePanel
                  lead={activeLead}
                  serviceWindow={serviceWindow}
                  guidance={guidance}
                />
              )}
            </main>
          )}
        </>
      )}
    </div>
  );
}
