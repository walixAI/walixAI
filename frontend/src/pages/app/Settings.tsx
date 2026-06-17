/**
 * Settings — Configuración del workspace.
 *
 * Tabs (via ?tab=<name>):
 *   bot        — Bot IA: system prompt, tono, preguntas de calificación
 *   kb         — Base de conocimiento del bot
 *   whatsapp   — Integración Meta Lead Ads
 *
 * Rutas relacionadas:
 *   /settings/team — Equipo (enlace en sidebar, página propia)
 */
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bot, BookOpen, Zap, CheckCircle2, Copy, ChevronLeft, ChevronRight,
  Loader2, Pencil, RefreshCw, Plus, Trash2, Unplug, X, Save,
} from "lucide-react";
import { toast } from "sonner";
import { api, type MetaConfigIn, type KBDocumentListItem } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { useTenantLabels } from "@/hooks/useTenantLabels";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const WEBHOOK_URL = `${BASE_URL}/api/webhooks/meta-leads`;

const TONE_OPTIONS = [
  { value: "amigable",    label: "Amigable",    desc: "Cercano y cálido" },
  { value: "profesional", label: "Profesional", desc: "Claro y directo" },
  { value: "formal",      label: "Formal",      desc: "Institucional" },
  { value: "cercano",     label: "Cercano",     desc: "Como un conocido de confianza" },
];

const TABS = [
  { key: "bot",       label: "Bot IA",              icon: Bot },
  { key: "kb",        label: "Base de conocimiento", icon: BookOpen },
  { key: "whatsapp",  label: "WhatsApp / Meta",     icon: Zap },
] as const;

// ── Row helper ────────────────────────────────────────────────────────────────

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="px-3 py-2 flex justify-between gap-4 items-start">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className={cn("text-xs font-medium text-right break-all", mono && "font-mono text-[11px]")}>{value}</span>
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════════════════════╗
// ║  TAB: BOT                                                                  ║
// ╚══════════════════════════════════════════════════════════════════════════════╝

function BotTab({ branchId }: { branchId: string }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { entities } = useTenantLabels();

  const { data: botConfig, isLoading } = useQuery({
    queryKey: ["bot-config", branchId],
    queryFn: () => api.getBotConfig(branchId),
    enabled: !!branchId,
  });

  // Local draft state (all-at-once save)
  const [promptDraft, setPromptDraft] = useState<string | null>(null);
  const [toneDraft, setToneDraft] = useState<string | null>(null);
  const [questionsDraft, setQuestionsDraft] = useState<
    Array<{ order: number; question: string; field_key: string }> | null
  >(null);

  const currentPrompt   = promptDraft    ?? botConfig?.system_prompt     ?? "";
  const currentTone     = toneDraft      ?? botConfig?.tone              ?? "amigable";
  const currentQuestions = questionsDraft ?? botConfig?.qualification_questions ?? [];

  const isDirty = promptDraft !== null || toneDraft !== null || questionsDraft !== null;

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateBotConfig(branchId, {
        system_prompt: currentPrompt,
        tone: currentTone,
        qualification_questions: currentQuestions,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bot-config", branchId] });
      setPromptDraft(null);
      setToneDraft(null);
      setQuestionsDraft(null);
      toast.success("Configuración guardada. Los cambios aplican en el próximo mensaje.");
    },
    onError: () => toast.error("Error al guardar"),
  });

  const regenMutation = useMutation({
    mutationFn: () => api.regenerateBotConfig(branchId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bot-config", branchId] });
      setPromptDraft(null);
      setToneDraft(null);
      setQuestionsDraft(null);
      toast.success("Configuración regenerada desde la descripción del negocio");
    },
    onError: () => toast.error("No hay descripción disponible para regenerar"),
  });

  function handleRegen() {
    if (isDirty && !window.confirm("¿Regenerar? Perderás los cambios manuales.")) return;
    regenMutation.mutate();
  }

  function addQuestion() {
    if (currentQuestions.length >= 7) {
      toast.error("Máximo 7 preguntas de calificación");
      return;
    }
    const next = [...currentQuestions, { order: currentQuestions.length + 1, question: "", field_key: "" }];
    setQuestionsDraft(next);
  }

  function removeQuestion(i: number) {
    const next = currentQuestions
      .filter((_, idx) => idx !== i)
      .map((q, idx) => ({ ...q, order: idx + 1 }));
    setQuestionsDraft(next);
  }

  function updateQuestion(i: number, field: "question" | "field_key", val: string) {
    const next = currentQuestions.map((q, idx) =>
      idx === i ? { ...q, [field]: val } : q
    );
    setQuestionsDraft(next);
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Cargando configuración…
      </div>
    );
  }

  if (!botConfig?.system_prompt) {
    // No config yet
    return (
      <div className="py-8 space-y-4">
        {botConfig?.onboarding_description ? (
          <>
            <p className="text-sm text-muted-foreground">
              El onboarding está completo. Genera la configuración inicial del bot con IA.
            </p>
            <Button size="sm" onClick={handleRegen} disabled={regenMutation.isPending}>
              {regenMutation.isPending
                ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
              Generar configuración del bot con IA
            </Button>
          </>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Primero completa el onboarding para que Walix conozca tu negocio y configure el bot automáticamente.
            </p>
            <Button size="sm" onClick={() => navigate(`/onboarding/new?branch_id=${branchId}`)}>
              <Bot className="h-3.5 w-3.5 mr-1.5" />
              Iniciar onboarding
            </Button>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* §A — Status banner */}
      {botConfig.is_auto_generated ? (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          Esta configuración fue generada automáticamente desde tu onboarding. Puedes editarla cuando quieras.
        </div>
      ) : botConfig.bot_config_updated_at ? (
        <p className="text-xs text-muted-foreground">
          Última edición manual: {new Date(botConfig.bot_config_updated_at).toLocaleDateString("es-MX", { dateStyle: "long" })}
        </p>
      ) : null}

      {/* §B — System prompt */}
      <div className="space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div>
            <Label className="text-sm font-semibold">Instrucciones del bot</Label>
            <p className="text-xs text-muted-foreground mt-0.5">
              Define cómo se presenta tu bot y cuándo transfiere la conversación a un humano.
            </p>
          </div>
          <button
            onClick={handleRegen}
            disabled={regenMutation.isPending}
            className="text-[11px] text-muted-foreground hover:text-primary flex items-center gap-1 shrink-0 transition-colors mt-0.5"
          >
            {regenMutation.isPending
              ? <Loader2 className="h-3 w-3 animate-spin" />
              : <RefreshCw className="h-3 w-3" />}
            ↺ Regenerar
          </button>
        </div>
        <Textarea
          value={currentPrompt}
          onChange={(e) => setPromptDraft(e.target.value)}
          rows={9}
          className="text-sm font-mono resize-none"
          placeholder="Describe cómo debe comportarse tu bot…"
        />
      </div>

      {/* §C — Tone */}
      <div className="space-y-2">
        <Label className="text-sm font-semibold">Tono de comunicación</Label>
        <div className="grid grid-cols-2 gap-2">
          {TONE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setToneDraft(opt.value)}
              className={cn(
                "flex flex-col items-start text-left rounded-lg border px-3 py-2.5 transition-all text-sm",
                currentTone === opt.value
                  ? "border-primary bg-primary/5 text-primary"
                  : "border-border hover:border-primary/40"
              )}
            >
              <span className="font-semibold">{opt.label}</span>
              <span className="text-xs text-muted-foreground">{opt.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* §D — Questions */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-sm font-semibold">
              Preguntas para calificar a tus {entities}
            </Label>
            <p className="text-xs text-muted-foreground mt-0.5">
              Máximo 7 preguntas. El bot las hace en orden.
            </p>
          </div>
          <span className="text-[11px] text-muted-foreground">
            {currentQuestions.length}/7
          </span>
        </div>

        <div className="space-y-2">
          {currentQuestions.map((q, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="text-xs font-bold text-muted-foreground mt-2.5 w-4 shrink-0">
                {q.order}.
              </span>
              <div className="flex-1 space-y-1">
                <Input
                  value={q.question}
                  onChange={(e) => updateQuestion(i, "question", e.target.value)}
                  placeholder="¿Cuál es el motivo de tu consulta?"
                  className="text-sm h-8"
                />
                <Input
                  value={q.field_key}
                  onChange={(e) => updateQuestion(i, "field_key", e.target.value)}
                  placeholder="motivo_consulta"
                  className="text-xs h-7 font-mono text-muted-foreground"
                />
              </div>
              <button
                onClick={() => removeQuestion(i)}
                className="mt-1.5 text-muted-foreground hover:text-danger transition-colors shrink-0"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>

        {currentQuestions.length < 7 && (
          <Button variant="outline" size="sm" className="gap-1.5" onClick={addQuestion}>
            <Plus className="h-3.5 w-3.5" />
            Agregar pregunta
          </Button>
        )}
      </div>

      {/* Save */}
      <div className="pt-2 flex items-center gap-3">
        <Button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || !isDirty}
          className="gap-1.5"
        >
          {saveMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          <Save className="h-3.5 w-3.5" />
          Guardar configuración del bot
        </Button>
        {isDirty && (
          <button
            className="text-xs text-muted-foreground hover:text-foreground"
            onClick={() => { setPromptDraft(null); setToneDraft(null); setQuestionsDraft(null); }}
          >
            Descartar cambios
          </button>
        )}
      </div>
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════════════════════╗
// ║  TAB: KNOWLEDGE BASE                                                       ║
// ╚══════════════════════════════════════════════════════════════════════════════╝

function KBModal({
  open,
  doc,
  onClose,
}: {
  open: boolean;
  doc: KBDocumentListItem | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [title, setTitle] = useState(doc?.title ?? "");
  const [content, setContent] = useState("");

  // Load content when editing existing doc
  const { data: detail, isLoading: loadingDetail } = useQuery({
    queryKey: ["kb-doc-detail", doc?.id],
    queryFn: () => api.getKBDocument(doc!.id),
    enabled: !!doc?.id && open,
  });

  const resolvedContent = content || detail?.content || "";

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (doc) {
        return api.updateKBDocument(doc.id, { title, content: resolvedContent });
      }
      return api.createKBDocument({ title, content: resolvedContent });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kb-documents"] });
      toast.success("Documento guardado. Tu bot ya puede usar esta información.");
      onClose();
    },
    onError: () => toast.error("Error al guardar (verifica OPENAI_API_KEY)"),
  });

  // Reset state on open
  const handleOpen = (isOpen: boolean) => {
    if (isOpen) {
      setTitle(doc?.title ?? "");
      setContent("");
    } else {
      onClose();
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{doc ? "Editar documento" : "Agregar documento"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label>Título</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="ej. Preguntas frecuentes"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label>Contenido</Label>
            {loadingDetail ? (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
              </div>
            ) : (
              <Textarea
                value={content || detail?.content || ""}
                onChange={(e) => setContent(e.target.value)}
                rows={8}
                className="text-sm"
                placeholder={"Ejemplo: Horarios de atención: Lunes a Viernes de 9am a 6pm.\nSábados de 10am a 2pm. Domingos cerrado.\n\nServicios: consulta de endocrinología pediátrica, control de diabetes, etc."}
              />
            )}
            <p className="text-[11px] text-muted-foreground">
              Mínimo 10 caracteres. Se generará el embedding automáticamente (2-3 segundos).
            </p>
          </div>
          <div className="flex gap-2 pt-1">
            <Button
              className="flex-1"
              disabled={!title || resolvedContent.length < 10 || saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
            >
              {saveMutation.isPending
                ? <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />Indexando…</>
                : "Guardar documento"}
            </Button>
            <Button variant="outline" onClick={onClose}>Cancelar</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function KBTab({ branchId }: { branchId: string }) {
  const qc = useQueryClient();
  const [modalDoc, setModalDoc] = useState<KBDocumentListItem | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const regenMutation = useMutation({
    mutationFn: () => api.regenerateBotConfig(branchId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kb-documents"] });
      toast.success("Documento inicial generado desde tu descripción de negocio");
    },
    onError: () => toast.error("No hay descripción disponible para generar el documento"),
  });

  const { data: docs, isLoading } = useQuery({
    queryKey: ["kb-documents"],
    queryFn: () => api.listKBDocuments({ limit: 50 }),
    staleTime: 30_000,
  });

  const deleteMutation = useMutation({
    mutationFn: async (doc: KBDocumentListItem) => {
      const res = await api.deleteKBDocument(doc.id);
      if (!res.deleted && res.warning) {
        if (!window.confirm(`⚠️ ${res.warning}\n\n¿Eliminar de todas formas?`)) {
          throw new Error("cancelled");
        }
        await api.deleteKBDocument(doc.id, true);
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kb-documents"] });
      toast.success("Documento eliminado");
    },
    onError: (e: Error) => { if (e.message !== "cancelled") toast.error("Error al eliminar"); },
  });

  function openAdd() { setModalDoc(null); setModalOpen(true); }
  function openEdit(doc: KBDocumentListItem) { setModalDoc(doc); setModalOpen(true); }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold">Base de conocimiento del bot</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Documentos que tu bot usa para responder preguntas específicas sobre tu negocio
            (servicios, precios, horarios, políticas, etc.)
          </p>
        </div>
        <Button size="sm" className="gap-1.5 shrink-0" onClick={openAdd}>
          <Plus className="h-3.5 w-3.5" />
          Agregar
        </Button>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Cargando documentos…
        </div>
      ) : docs && docs.length > 0 ? (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground">Título</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-muted-foreground hidden sm:table-cell">Vista previa</th>
                <th className="text-right px-4 py-2.5 text-xs font-semibold text-muted-foreground">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {docs.map((doc) => (
                <tr key={doc.id} className="hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium truncate max-w-[160px]">{doc.title}</span>
                      {doc.is_auto_generated && (
                        <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-primary/10 text-primary shrink-0">
                          AUTO
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-muted-foreground mt-0.5">{doc.chunk_count} fragmentos</p>
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell">
                    <p className="text-xs text-muted-foreground line-clamp-2 max-w-[240px]">
                      {doc.content_preview ?? "—"}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => openEdit(doc)}
                        className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                      >
                        <Pencil className="h-3 w-3" /> Editar
                      </button>
                      <button
                        onClick={() => deleteMutation.mutate(doc)}
                        disabled={deleteMutation.isPending}
                        className="text-xs text-muted-foreground hover:text-danger flex items-center gap-1 transition-colors"
                        title={doc.is_auto_generated ? "Pedirá confirmación" : "Eliminar"}
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-4 py-12 text-center border border-dashed border-border rounded-xl">
          <BookOpen className="h-10 w-10 text-muted-foreground/40" />
          <div className="space-y-1">
            <p className="text-sm font-medium">Tu bot no tiene base de conocimiento aún</p>
            <p className="text-xs text-muted-foreground">
              Agrega documentos para que el bot responda preguntas específicas de tu negocio.
            </p>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={openAdd}>
              <Plus className="h-3.5 w-3.5 mr-1.5" />
              Agregar documento
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => regenMutation.mutate()}
              disabled={regenMutation.isPending}
            >
              {regenMutation.isPending
                ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
              Generar desde descripción
            </Button>
          </div>
        </div>
      )}

      <KBModal
        open={modalOpen}
        doc={modalDoc}
        onClose={() => { setModalOpen(false); setModalDoc(null); }}
      />
    </div>
  );
}

// ╔══════════════════════════════════════════════════════════════════════════════╗
// ║  TAB: WHATSAPP / META LEAD ADS (código existente movido aquí)              ║
// ╚══════════════════════════════════════════════════════════════════════════════╝

const DEFAULT_MAPPING = { full_name: "name", phone_number: "wa_phone", city: "parent_city" };
const WA_STEPS = [
  { n: 1, label: "Page ID" },
  { n: 2, label: "Access Token" },
  { n: 3, label: "Formularios" },
  { n: 4, label: "Webhook" },
  { n: 5, label: "Confirmar" },
];

interface WaFormData { page_id: string; page_access_token: string; form_ids_raw: string }

function WaStepPageId({ v, set }: { v: string; set: (s: string) => void }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Facebook → tu Página → Información → <span className="font-medium text-foreground">ID de página</span>
      </p>
      <div className="space-y-1.5">
        <Label>Page ID</Label>
        <Input placeholder="123456789012345" value={v} onChange={(e) => set(e.target.value)} autoFocus />
      </div>
    </div>
  );
}

function WaStepToken({ v, set }: { v: string; set: (s: string) => void }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        developers.facebook.com → tu app → WhatsApp → API Setup → System User con permiso{" "}
        <code className="text-xs bg-muted px-1 rounded">leads_retrieval</code>
      </p>
      <div className="space-y-1.5">
        <Label>Page Access Token</Label>
        <Input type="password" placeholder="EAA..." value={v} onChange={(e) => set(e.target.value)} autoFocus />
      </div>
    </div>
  );
}

function WaStepFormIds({ v, set }: { v: string; set: (s: string) => void }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Meta Business Suite → Formularios para clientes potenciales → copia los IDs separados por coma.
      </p>
      <div className="space-y-1.5">
        <Label>IDs de formularios</Label>
        <Input placeholder="123456789, 987654321" value={v} onChange={(e) => set(e.target.value)} autoFocus />
        <p className="text-[11px] text-muted-foreground">Separa múltiples IDs con coma</p>
      </div>
    </div>
  );
}

function WaStepWebhook({ verifyToken }: { verifyToken?: string }) {
  function copy(text: string, label: string) {
    navigator.clipboard.writeText(text).then(() => toast.success(`${label} copiado`));
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">Meta Developers → WhatsApp → Webhooks</p>
      <div className="space-y-1.5">
        <Label>URL del webhook</Label>
        <div className="flex gap-2">
          <Input value={WEBHOOK_URL} readOnly className="font-mono text-xs bg-muted" />
          <Button variant="outline" size="icon" className="shrink-0" onClick={() => copy(WEBHOOK_URL, "URL")}>
            <Copy className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>Verify Token</Label>
        <div className="flex gap-2">
          <Input value={verifyToken ?? "—"} readOnly className="font-mono text-xs bg-muted" />
          {verifyToken && (
            <Button variant="outline" size="icon" className="shrink-0" onClick={() => copy(verifyToken, "Token")}>
              <Copy className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function WaStepConfirm({ data }: { data: WaFormData }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">Revisa la configuración antes de guardar.</p>
      <div className="border border-border rounded-lg divide-y divide-border">
        <Row label="Page ID" value={data.page_id} />
        <Row label="Access Token" value={"••••••••" + data.page_access_token.slice(-4)} />
        <Row label="Formularios" value={data.form_ids_raw ? data.form_ids_raw.split(",").filter(Boolean).length + " formulario(s)" : "Ninguno"} />
        <Row label="Webhook URL" value={WEBHOOK_URL} mono />
      </div>
    </div>
  );
}

function WaSetupWizard({ branchId, onDone }: { branchId: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<WaFormData>({ page_id: "", page_access_token: "", form_ids_raw: "" });
  const { data: existingConfig } = useQuery({ queryKey: ["meta-config", branchId], queryFn: () => api.getMetaConfig(branchId) });

  const saveMutation = useMutation({
    mutationFn: (payload: MetaConfigIn) => api.saveMetaConfig(branchId, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["meta-config", branchId] }); toast.success("Integración guardada"); onDone(); },
    onError: (e: Error) => toast.error("Error al guardar", { description: e.message }),
  });

  function canNext() {
    if (step === 1) return form.page_id.trim().length > 0;
    if (step === 2) return form.page_access_token.trim().length > 0;
    return true;
  }

  function handleNext() {
    if (step < 5) { setStep(step + 1); return; }
    saveMutation.mutate({ page_id: form.page_id.trim(), page_access_token: form.page_access_token.trim(), form_ids: form.form_ids_raw.split(",").map((s) => s.trim()).filter(Boolean), field_mapping: DEFAULT_MAPPING });
  }

  const stepContent: Record<number, React.ReactNode> = {
    1: <WaStepPageId v={form.page_id} set={(v) => setForm((f) => ({ ...f, page_id: v }))} />,
    2: <WaStepToken v={form.page_access_token} set={(v) => setForm((f) => ({ ...f, page_access_token: v }))} />,
    3: <WaStepFormIds v={form.form_ids_raw} set={(v) => setForm((f) => ({ ...f, form_ids_raw: v }))} />,
    4: <WaStepWebhook verifyToken={existingConfig?.verify_token} />,
    5: <WaStepConfirm data={form} />,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-1">
        {WA_STEPS.map((s, i) => (
          <div key={s.n} className="flex items-center gap-1">
            <div className={cn("w-6 h-6 rounded-full text-[11px] font-bold flex items-center justify-center shrink-0", s.n < step ? "bg-emerald-500 text-white" : s.n === step ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
              {s.n < step ? <CheckCircle2 className="h-3.5 w-3.5" /> : s.n}
            </div>
            {i < WA_STEPS.length - 1 && <div className={cn("h-0.5 flex-1 w-6 rounded-full", s.n < step ? "bg-emerald-500" : "bg-muted")} />}
          </div>
        ))}
      </div>
      <div>
        <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">Paso {step} de {WA_STEPS.length}</p>
        <h3 className="text-base font-semibold mt-0.5">{["Page ID de Facebook", "Page Access Token", "IDs de formularios", "URL del webhook", "Confirmar configuración"][step - 1]}</h3>
      </div>
      <div>{stepContent[step]}</div>
      <div className="flex gap-2 pt-2">
        {step > 1 && (
          <Button variant="outline" size="sm" onClick={() => setStep(step - 1)} disabled={saveMutation.isPending}>
            <ChevronLeft className="h-4 w-4 mr-1" /> Atrás
          </Button>
        )}
        <Button size="sm" className="ml-auto" onClick={handleNext} disabled={!canNext() || saveMutation.isPending}>
          {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : step === 5 ? "Guardar" : <><ChevronRight className="h-4 w-4 ml-1" /></>}
          {step < 5 && "Siguiente"}
        </Button>
      </div>
    </div>
  );
}

function WaConnectedCard({ config, branchId, onEdit }: { config: NonNullable<Awaited<ReturnType<typeof api.getMetaConfig>>>; branchId: string; onEdit: () => void }) {
  const qc = useQueryClient();
  const disconnect = useMutation({
    mutationFn: () => api.deleteMetaConfig(branchId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["meta-config", branchId] }); toast.success("Integración desconectada"); },
    onError: (e: Error) => toast.error("Error", { description: e.message }),
  });
  function copy(text: string, label: string) { navigator.clipboard.writeText(text).then(() => toast.success(`${label} copiado`)); }
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-emerald-600"><CheckCircle2 className="h-4 w-4" /><span className="text-sm font-semibold">Conectado</span></div>
      <div className="border border-border rounded-lg divide-y divide-border">
        <Row label="Page ID" value={config.page_id} />
        <Row label="Formularios" value={config.form_ids.length ? config.form_ids.join(", ") : "Ninguno"} />
        <Row label="Webhook URL" value={WEBHOOK_URL} mono />
        <Row label="Verify Token" value={config.verify_token} mono />
      </div>
      <div className="flex gap-2 pt-1">
        <Button variant="outline" size="sm" onClick={() => copy(WEBHOOK_URL, "URL")}><Copy className="h-3.5 w-3.5 mr-1" />Copiar URL</Button>
        <Button variant="outline" size="sm" onClick={onEdit}><Pencil className="h-3.5 w-3.5 mr-1" />Editar</Button>
        <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive ml-auto" onClick={() => disconnect.mutate()} disabled={disconnect.isPending}>
          {disconnect.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Unplug className="h-3.5 w-3.5 mr-1" />}Desconectar
        </Button>
      </div>
    </div>
  );
}

function WhatsAppTab({ branchId, canManage }: { branchId: string; canManage: boolean }) {
  const [editing, setEditing] = useState(false);
  const { data: config, isLoading } = useQuery({ queryKey: ["meta-config", branchId], queryFn: () => api.getMetaConfig(branchId), enabled: !!branchId && canManage });
  const isConnected = !!config && config.is_active;

  if (!canManage) return <p className="text-sm text-muted-foreground py-4">Solo owner o IT pueden gestionar esta integración.</p>;
  if (isLoading) return <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Cargando…</div>;
  if (!branchId) return <p className="text-sm text-muted-foreground py-4">No se encontraron sucursales.</p>;
  if (isConnected && !editing) return <WaConnectedCard config={config} branchId={branchId} onEdit={() => setEditing(true)} />;
  return <WaSetupWizard branchId={branchId} onDone={() => setEditing(false)} />;
}

// ╔══════════════════════════════════════════════════════════════════════════════╗
// ║  MAIN PAGE                                                                 ║
// ╚══════════════════════════════════════════════════════════════════════════════╝

export default function Settings() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get("tab") ?? "bot") as "bot" | "kb" | "whatsapp";
  const canManage = user?.role === "owner" || user?.role === "it" || user?.role === "gerente";

  // Branch resolution
  const needsBranchSelect = (user?.role === "owner" || user?.role === "it") && !user?.branch_id;
  const { data: branches = [] } = useQuery({
    queryKey: ["branches"],
    queryFn: () => api.listBranches(),
    enabled: needsBranchSelect,
  });
  const [selectedBranchId, setSelectedBranchId] = useState<string>("");
  const branchId = user?.branch_id ?? selectedBranchId || (branches[0]?.id ?? "");

  function setTab(tab: string) {
    setSearchParams({ tab });
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Configuración</h1>
        <p className="text-sm text-muted-foreground mt-1">Bot, base de conocimiento e integraciones.</p>
      </div>

      {/* Branch selector (owner/IT without fixed branch) */}
      {needsBranchSelect && branches.length > 1 && (
        <div className="flex items-center gap-3">
          <Label className="text-xs shrink-0">Sucursal:</Label>
          <Select value={branchId} onValueChange={setSelectedBranchId}>
            <SelectTrigger className="h-8 text-sm max-w-[220px]">
              <SelectValue placeholder="Selecciona una sucursal" />
            </SelectTrigger>
            <SelectContent>
              {branches.map((b) => (
                <SelectItem key={b.id} value={b.id} className="text-sm">{b.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-0.5 bg-muted rounded-lg p-1">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all",
              activeTab === key
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-3.5 w-3.5 shrink-0" />
            <span className="hidden sm:inline">{label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      {!canManage ? (
        <p className="text-sm text-muted-foreground py-4">Solo owner, gerente o IT pueden acceder a esta sección.</p>
      ) : !branchId ? (
        <p className="text-sm text-muted-foreground py-4">No se encontraron sucursales en tu cuenta.</p>
      ) : (
        <div className="rounded-xl border border-border bg-card p-5 shadow-card">
          {activeTab === "bot"      && <BotTab branchId={branchId} />}
          {activeTab === "kb"       && <KBTab branchId={branchId} />}
          {activeTab === "whatsapp" && <WhatsAppTab branchId={branchId} canManage={canManage} />}
        </div>
      )}
    </div>
  );
}
