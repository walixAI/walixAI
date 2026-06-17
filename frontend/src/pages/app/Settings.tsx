import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, ChevronRight, ChevronLeft, Loader2, Pencil, Unplug, Zap, Bot, Settings2, RefreshCw, Plus, Trash2, BookOpen } from "lucide-react";
import { toast } from "sonner";
import { api, type MetaConfigIn } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const WEBHOOK_URL = `${BASE_URL}/api/webhooks/meta-leads`;

const DEFAULT_MAPPING = { full_name: "name", phone_number: "wa_phone", city: "parent_city" };

const STEPS = [
  { n: 1, label: "Page ID" },
  { n: 2, label: "Access Token" },
  { n: 3, label: "Formularios" },
  { n: 4, label: "Webhook" },
  { n: 5, label: "Confirmar" },
];

interface FormData {
  page_id: string;
  page_access_token: string;
  form_ids_raw: string; // comma-separated, joined on save
}

// ── Step components ────────────────────────────────────────────────────────────

function StepPageId({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Lo encuentras en <span className="font-medium text-foreground">Facebook → tu Página → Información → ID de página</span>
      </p>
      <div className="space-y-1.5">
        <Label htmlFor="page_id">Page ID</Label>
        <Input
          id="page_id"
          placeholder="123456789012345"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoFocus
        />
      </div>
    </div>
  );
}

function StepToken({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Ve a <span className="font-medium text-foreground">developers.facebook.com → tu app → WhatsApp → API Setup</span> y genera un token permanente con un System User con permiso{" "}
        <code className="text-xs bg-muted px-1 py-0.5 rounded">leads_retrieval</code>.
      </p>
      <div className="space-y-1.5">
        <Label htmlFor="token">Page Access Token</Label>
        <Input
          id="token"
          type="password"
          placeholder="EAA..."
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoFocus
        />
      </div>
    </div>
  );
}

function StepFormIds({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        En <span className="font-medium text-foreground">Meta Business Suite → Formularios para clientes potenciales</span>, copia los IDs de los formularios activos y pégalos separados por coma.
      </p>
      <div className="space-y-1.5">
        <Label htmlFor="form_ids">IDs de formularios</Label>
        <Input
          id="form_ids"
          placeholder="123456789, 987654321"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoFocus
        />
        <p className="text-[11px] text-muted-foreground">Separa múltiples IDs con coma</p>
      </div>
    </div>
  );
}

function StepWebhook({ verifyToken }: { verifyToken?: string }) {
  function copy(text: string, label: string) {
    navigator.clipboard.writeText(text).then(() => toast.success(`${label} copiado`));
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Pega estos valores en <span className="font-medium text-foreground">Meta Developers → WhatsApp → Webhooks</span> al configurar el webhook.
      </p>
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
          <Input
            value={verifyToken ?? "—"}
            readOnly
            className="font-mono text-xs bg-muted"
          />
          {verifyToken && (
            <Button variant="outline" size="icon" className="shrink-0" onClick={() => copy(verifyToken, "Token")}>
              <Copy className="h-4 w-4" />
            </Button>
          )}
        </div>
        <p className="text-[11px] text-muted-foreground">
          El Verify Token está configurado en tus variables de entorno del backend (<code className="bg-muted px-1 py-0.5 rounded">META_VERIFY_TOKEN</code>).
        </p>
      </div>
    </div>
  );
}

function StepConfirm({ data }: { data: FormData }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">Revisa la configuración antes de guardar.</p>
      <div className="border border-border rounded-lg divide-y divide-border">
        <Row label="Page ID" value={data.page_id} />
        <Row label="Access Token" value={"••••••••" + data.page_access_token.slice(-4)} />
        <Row
          label="Formularios"
          value={
            data.form_ids_raw
              ? data.form_ids_raw.split(",").filter(Boolean).length + " formulario(s)"
              : "Ninguno"
          }
        />
        <Row label="Webhook URL" value={WEBHOOK_URL} mono />
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="px-3 py-2 flex justify-between gap-4 items-start">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className={cn("text-xs font-medium text-right break-all", mono && "font-mono text-[11px]")}>{value}</span>
    </div>
  );
}

// ── Wizard ─────────────────────────────────────────────────────────────────────

function SetupWizard({ branchId, onDone }: { branchId: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<FormData>({ page_id: "", page_access_token: "", form_ids_raw: "" });

  // Fetch verify_token lazily (reuse query data if already loaded)
  const { data: existingConfig } = useQuery({
    queryKey: ["meta-config", branchId],
    queryFn: () => api.getMetaConfig(branchId),
  });

  const saveMutation = useMutation({
    mutationFn: (payload: MetaConfigIn) => api.saveMetaConfig(branchId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["meta-config", branchId] });
      toast.success("Integración guardada correctamente");
      onDone();
    },
    onError: (e: Error) => toast.error("Error al guardar", { description: e.message }),
  });

  function canNext() {
    if (step === 1) return form.page_id.trim().length > 0;
    if (step === 2) return form.page_access_token.trim().length > 0;
    return true;
  }

  function handleNext() {
    if (step < 5) { setStep(step + 1); return; }
    // Step 5 → save
    const form_ids = form.form_ids_raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    saveMutation.mutate({
      page_id: form.page_id.trim(),
      page_access_token: form.page_access_token.trim(),
      form_ids,
      field_mapping: DEFAULT_MAPPING,
    });
  }

  const stepContent: Record<number, React.ReactNode> = {
    1: <StepPageId value={form.page_id} onChange={(v) => setForm((f) => ({ ...f, page_id: v }))} />,
    2: <StepToken value={form.page_access_token} onChange={(v) => setForm((f) => ({ ...f, page_access_token: v }))} />,
    3: <StepFormIds value={form.form_ids_raw} onChange={(v) => setForm((f) => ({ ...f, form_ids_raw: v }))} />,
    4: <StepWebhook verifyToken={existingConfig?.verify_token} />,
    5: <StepConfirm data={form} />,
  };

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center gap-1">
        {STEPS.map((s, i) => (
          <div key={s.n} className="flex items-center gap-1">
            <div
              className={cn(
                "w-6 h-6 rounded-full text-[11px] font-bold flex items-center justify-center shrink-0",
                s.n < step
                  ? "bg-emerald-500 text-white"
                  : s.n === step
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground"
              )}
            >
              {s.n < step ? <CheckCircle2 className="h-3.5 w-3.5" /> : s.n}
            </div>
            {i < STEPS.length - 1 && (
              <div className={cn("h-0.5 flex-1 w-6 rounded-full", s.n < step ? "bg-emerald-500" : "bg-muted")} />
            )}
          </div>
        ))}
      </div>

      {/* Step label */}
      <div>
        <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
          Paso {step} de {STEPS.length}
        </p>
        <h3 className="text-base font-semibold mt-0.5">
          {step === 1 && "Page ID de Facebook"}
          {step === 2 && "Page Access Token"}
          {step === 3 && "IDs de formularios activos"}
          {step === 4 && "URL del webhook"}
          {step === 5 && "Confirmar configuración"}
        </h3>
      </div>

      {/* Content */}
      <div>{stepContent[step]}</div>

      {/* Nav buttons */}
      <div className="flex gap-2 pt-2">
        {step > 1 && (
          <Button variant="outline" size="sm" onClick={() => setStep(step - 1)} disabled={saveMutation.isPending}>
            <ChevronLeft className="h-4 w-4 mr-1" />
            Atrás
          </Button>
        )}
        <Button
          size="sm"
          className="ml-auto"
          onClick={handleNext}
          disabled={!canNext() || saveMutation.isPending}
        >
          {saveMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin mr-1" />
          ) : step === 5 ? (
            "Guardar configuración"
          ) : (
            <>
              Siguiente
              <ChevronRight className="h-4 w-4 ml-1" />
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

// ── Connected summary ─────────────────────────────────────────────────────────

function ConnectedCard({
  config,
  branchId,
  onEdit,
}: {
  config: NonNullable<Awaited<ReturnType<typeof api.getMetaConfig>>>;
  branchId: string;
  onEdit: () => void;
}) {
  const qc = useQueryClient();

  const disconnectMutation = useMutation({
    mutationFn: () => api.deleteMetaConfig(branchId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["meta-config", branchId] });
      toast.success("Integración desconectada");
    },
    onError: (e: Error) => toast.error("Error", { description: e.message }),
  });

  function copy(text: string, label: string) {
    navigator.clipboard.writeText(text).then(() => toast.success(`${label} copiado`));
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-emerald-600">
        <CheckCircle2 className="h-4 w-4" />
        <span className="text-sm font-semibold">Conectado</span>
      </div>

      <div className="border border-border rounded-lg divide-y divide-border">
        <Row label="Page ID" value={config.page_id} />
        <Row
          label="Formularios"
          value={config.form_ids.length ? config.form_ids.join(", ") : "Ninguno"}
        />
        <Row label="Webhook URL" value={WEBHOOK_URL} mono />
        <Row label="Verify Token" value={config.verify_token} mono />
      </div>

      <div className="flex gap-2 pt-1">
        <Button variant="outline" size="sm" onClick={() => copy(WEBHOOK_URL, "URL")}>
          <Copy className="h-3.5 w-3.5 mr-1" />
          Copiar URL
        </Button>
        <Button variant="outline" size="sm" onClick={onEdit}>
          <Pencil className="h-3.5 w-3.5 mr-1" />
          Editar
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="text-destructive hover:text-destructive ml-auto"
          onClick={() => disconnectMutation.mutate()}
          disabled={disconnectMutation.isPending}
        >
          {disconnectMutation.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
          ) : (
            <Unplug className="h-3.5 w-3.5 mr-1" />
          )}
          Desconectar
        </Button>
      </div>
    </div>
  );
}

// ── Bot config card ────────────────────────────────────────────────────────────

const TONE_OPTIONS = [
  { value: "amigable",    label: "Amigable — cercano y cálido" },
  { value: "profesional", label: "Profesional — claro y directo" },
  { value: "formal",      label: "Formal — institucional" },
  { value: "cercano",     label: "Cercano — como un conocido de confianza" },
];

function BotConfigCard({ branchId, canManage }: { branchId: string; canManage: boolean }) {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: botConfig, isLoading } = useQuery({
    queryKey: ["bot-config", branchId],
    queryFn: () => api.getBotConfig(branchId),
    enabled: !!branchId && canManage,
  });

  const [editingPrompt, setEditingPrompt] = useState(false);
  const [promptDraft, setPromptDraft] = useState("");
  const [toneDraft, setToneDraft] = useState("");

  // KB fragment state
  const [showAddFragment, setShowAddFragment] = useState(false);
  const [fragTitle, setFragTitle] = useState("");
  const [fragContent, setFragContent] = useState("");

  const saveMutation = useMutation({
    mutationFn: (data: Parameters<typeof api.updateBotConfig>[1]) =>
      api.updateBotConfig(branchId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bot-config", branchId] });
      setEditingPrompt(false);
      toast.success("Configuración guardada");
    },
    onError: () => toast.error("Error al guardar"),
  });

  const regenMutation = useMutation({
    mutationFn: () => api.regenerateBotConfig(branchId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bot-config", branchId] });
      toast.success("Config regenerada desde la descripción del negocio");
    },
    onError: () => toast.error("No hay descripción disponible para regenerar"),
  });

  const addFragMutation = useMutation({
    mutationFn: () => api.addKBFragment({ title: fragTitle, content: fragContent }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kb-status"] });
      setShowAddFragment(false);
      setFragTitle("");
      setFragContent("");
      toast.success("Fragmento agregado al Knowledge Base");
    },
    onError: () => toast.error("Error al agregar fragmento (verifica OPENAI_API_KEY)"),
  });

  const { data: kbStatus } = useQuery({
    queryKey: ["kb-status"],
    queryFn: () => api.getKBStatus(),
    enabled: canManage,
    staleTime: 60_000,
  });

  const deleteFragMutation = useMutation({
    mutationFn: (docId: string) => api.deleteKBFragment(docId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kb-status"] });
      toast.success("Fragmento eliminado");
    },
  });

  const hasGeneratedConfig = !!botConfig?.bot_system_prompt;

  return (
    <div className="rounded-xl border border-border bg-card shadow-card divide-y divide-border">
      {/* Header */}
      <div className="p-5 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-primary flex items-center justify-center shrink-0">
            <Bot className="h-5 w-5 text-primary-foreground" />
          </div>
          <div>
            <h2 className="text-sm font-semibold">Bot IA — WhatsApp</h2>
            <p className="text-xs text-muted-foreground">
              {hasGeneratedConfig
                ? "Config generada automáticamente desde el onboarding. Puedes editarla aquí."
                : "Configura el agente de WhatsApp y los criterios de calificación."}
            </p>
          </div>
        </div>
        {hasGeneratedConfig && (
          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 shrink-0">
            Activo
          </span>
        )}
      </div>

      {!canManage ? (
        <div className="p-5">
          <p className="text-xs text-muted-foreground">Solo owner o IT pueden gestionar la config del bot.</p>
        </div>
      ) : isLoading ? (
        <div className="p-5 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Cargando...
        </div>
      ) : !hasGeneratedConfig ? (
        /* ── Sin config generada ── */
        <div className="p-5 space-y-3">
          {botConfig?.onboarding_description ? (
            <>
              <p className="text-xs text-muted-foreground">
                El onboarding está completo. Genera la config del bot automáticamente desde tu descripción del negocio.
              </p>
              <Button
                size="sm"
                onClick={() => regenMutation.mutate()}
                disabled={regenMutation.isPending}
              >
                {regenMutation.isPending
                  ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
                Generar config del bot con IA
              </Button>
            </>
          ) : (
            <>
              <p className="text-xs text-muted-foreground">
                Primero completa el onboarding para que Walix conozca tu negocio.
              </p>
              <Button size="sm" onClick={() => navigate(`/onboarding/new?branch_id=${branchId}`)}>
                <Bot className="h-3.5 w-3.5 mr-1.5" />
                Iniciar onboarding
              </Button>
            </>
          )}
        </div>
      ) : (
        /* ── Config generada — mostrar y editar ── */
        <>
          {/* Tono */}
          <div className="p-5 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Tono del bot</p>
            </div>
            <Select
              value={toneDraft || botConfig.bot_tone || "amigable"}
              onValueChange={(v) => {
                setToneDraft(v);
                saveMutation.mutate({ bot_tone: v });
              }}
              disabled={saveMutation.isPending}
            >
              <SelectTrigger className="h-8 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TONE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value} className="text-sm">{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* System prompt */}
          <div className="p-5 space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">System prompt</p>
              {!editingPrompt && (
                <button
                  onClick={() => { setPromptDraft(botConfig.bot_system_prompt ?? ""); setEditingPrompt(true); }}
                  className="text-xs text-primary hover:underline flex items-center gap-1"
                >
                  <Pencil className="h-3 w-3" /> Editar
                </button>
              )}
            </div>
            {editingPrompt ? (
              <div className="space-y-2">
                <Textarea
                  value={promptDraft}
                  onChange={(e) => setPromptDraft(e.target.value)}
                  rows={8}
                  className="text-sm font-mono"
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={saveMutation.isPending}
                    onClick={() => saveMutation.mutate({ bot_system_prompt: promptDraft })}
                  >
                    {saveMutation.isPending ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : null}
                    Guardar
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditingPrompt(false)}>
                    Cancelar
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-xs text-foreground/80 bg-muted rounded-lg p-3 leading-relaxed whitespace-pre-wrap font-mono">
                {botConfig.bot_system_prompt}
              </p>
            )}
          </div>

          {/* Preguntas de calificación */}
          {botConfig.bot_qualification_questions && botConfig.bot_qualification_questions.length > 0 && (
            <div className="p-5 space-y-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Preguntas de calificación</p>
              <div className="space-y-1.5">
                {botConfig.bot_qualification_questions.map((q, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <span className="text-xs font-bold text-muted-foreground mt-0.5 w-4 shrink-0">{q.order}.</span>
                    <div className="flex-1">
                      <p>{q.question}</p>
                      <p className="text-[10px] text-muted-foreground font-mono">{q.field_key}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Regenerar */}
          <div className="p-5">
            <button
              onClick={() => regenMutation.mutate()}
              disabled={regenMutation.isPending}
              className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1.5 transition-colors"
            >
              {regenMutation.isPending
                ? <Loader2 className="h-3 w-3 animate-spin" />
                : <RefreshCw className="h-3 w-3" />}
              Regenerar desde descripción del negocio
            </button>
            {botConfig.bot_config_generated_at && (
              <p className="text-[10px] text-muted-foreground/60 mt-1">
                Generado: {new Date(botConfig.bot_config_generated_at).toLocaleDateString("es-MX")}
                {botConfig.bot_config_updated_at && ` · Editado: ${new Date(botConfig.bot_config_updated_at).toLocaleDateString("es-MX")}`}
              </p>
            )}
          </div>
        </>
      )}

      {/* ── Knowledge Base ── */}
      <div className="p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-muted-foreground" />
            <p className="text-sm font-semibold">Knowledge Base</p>
            {kbStatus && (
              <span className="text-[11px] text-muted-foreground">
                {kbStatus.total_documents} doc{kbStatus.total_documents !== 1 ? "s" : ""} · {kbStatus.total_chunks} fragmentos
              </span>
            )}
          </div>
          {canManage && (
            <button
              onClick={() => setShowAddFragment(!showAddFragment)}
              className="text-xs text-primary hover:underline flex items-center gap-1"
            >
              <Plus className="h-3 w-3" /> Agregar texto
            </button>
          )}
        </div>

        {/* Add fragment form */}
        {showAddFragment && (
          <div className="border border-border rounded-lg p-4 space-y-3 bg-muted/30">
            <p className="text-xs text-muted-foreground">
              Pega cualquier texto que el bot deba conocer: preguntas frecuentes, servicios, precios, horarios...
            </p>
            <div className="space-y-1.5">
              <Label className="text-xs">Título</Label>
              <Input
                placeholder="ej. Servicios y precios"
                value={fragTitle}
                onChange={(e) => setFragTitle(e.target.value)}
                className="h-8 text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Contenido</Label>
              <Textarea
                placeholder="Escribe o pega el texto que el bot debe conocer..."
                value={fragContent}
                onChange={(e) => setFragContent(e.target.value)}
                rows={5}
                className="text-sm"
              />
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={!fragTitle || !fragContent || addFragMutation.isPending}
                onClick={() => addFragMutation.mutate()}
              >
                {addFragMutation.isPending && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
                Indexar en KB
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowAddFragment(false)}>
                Cancelar
              </Button>
            </div>
          </div>
        )}

        {/* Documents list */}
        {kbStatus && kbStatus.documents.length > 0 && (
          <div className="divide-y divide-border border border-border rounded-lg overflow-hidden">
            {kbStatus.documents.map((doc) => (
              <div key={doc.filename} className="flex items-center gap-3 px-4 py-2.5">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{doc.title}</p>
                  <p className="text-[10px] text-muted-foreground">{doc.chunk_count} fragmentos</p>
                </div>
                {canManage && "id" in doc && (
                  <button
                    onClick={() => deleteFragMutation.mutate((doc as { id: string }).id)}
                    disabled={deleteFragMutation.isPending}
                    className="text-muted-foreground hover:text-danger transition-colors shrink-0"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {kbStatus && kbStatus.documents.length === 0 && (
          <p className="text-xs text-muted-foreground">
            El Knowledge Base está vacío. Agrega textos para que el bot responda preguntas específicas de tu negocio.
          </p>
        )}
      </div>
    </div>
  );
}


// ── Main page ─────────────────────────────────────────────────────────────────

export default function Settings() {
  const { user } = useAuth();
  const canManage = user?.role === "owner" || user?.role === "it";
  const needsBranchSelect = canManage && !user?.branch_id;

  // For owner/IT with no branch_id: fetch all branches they can manage
  const { data: branches = [], isLoading: branchesLoading } = useQuery({
    queryKey: ["branches"],
    queryFn: () => api.listBranches(),
    enabled: needsBranchSelect,
  });

  // The active branch: from user profile if set, else first of fetched list
  const [selectedBranchId, setSelectedBranchId] = useState<string>("");
  const resolvedBranchId = selectedBranchId || (branches[0]?.id ?? "");
  const branchId = user?.branch_id ?? resolvedBranchId;

  const { data: config, isLoading: configLoading } = useQuery({
    queryKey: ["meta-config", branchId],
    queryFn: () => api.getMetaConfig(branchId),
    enabled: !!branchId && canManage,
  });

  const [editing, setEditing] = useState(false);
  const isLoading = branchesLoading || configLoading;
  const isConnected = !!config && config.is_active;

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Configuracion</h1>
        <p className="text-sm text-muted-foreground mt-1">Integraciones y configuracion de la cuenta.</p>
      </div>

      {/* Bot IA card */}
      {canManage && branchId && (
        <BotConfigCard branchId={branchId} canManage={canManage} />
      )}

      {/* Meta Lead Ads card */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-card space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-blue-600 flex items-center justify-center shrink-0">
              <Zap className="h-5 w-5 text-white" />
            </div>
            <div>
              <h2 className="text-sm font-semibold">Meta Lead Ads</h2>
              <p className="text-xs text-muted-foreground">
                Recibe leads automáticamente desde formularios de Facebook e Instagram.
              </p>
            </div>
          </div>
          <span
            className={cn(
              "text-[11px] font-semibold px-2 py-0.5 rounded-full shrink-0",
              isConnected
                ? "bg-emerald-100 text-emerald-700"
                : "bg-muted text-muted-foreground"
            )}
          >
            {isConnected ? "Conectado" : "No conectado"}
          </span>
        </div>

        {/* Branch selector — shown when owner/IT has no fixed branch */}
        {needsBranchSelect && branches.length > 0 && (
          <div className="space-y-1.5">
            <Label className="text-xs">Sucursal</Label>
            {branches.length === 1 ? (
              <p className="text-xs font-medium py-1">{branches[0].name}</p>
            ) : (
              <Select
                value={branchId}
                onValueChange={(v) => { setSelectedBranchId(v); setEditing(false); }}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="Selecciona una sucursal..." />
                </SelectTrigger>
                <SelectContent>
                  {branches.map((b) => (
                    <SelectItem key={b.id} value={b.id} className="text-xs">{b.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        )}

        {/* Body */}
        {!canManage ? (
          <p className="text-xs text-muted-foreground">
            Solo el owner o el equipo de IT puede gestionar esta integración.
          </p>
        ) : isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
            <Loader2 className="h-4 w-4 animate-spin" />
            Cargando configuración...
          </div>
        ) : !branchId ? (
          <p className="text-xs text-muted-foreground">No se encontraron sucursales en tu cuenta.</p>
        ) : isConnected && !editing ? (
          <ConnectedCard config={config} branchId={branchId} onEdit={() => setEditing(true)} />
        ) : (
          <SetupWizard branchId={branchId} onDone={() => setEditing(false)} />
        )}
      </div>
    </div>
  );
}
