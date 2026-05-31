import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, Loader2, Pencil, X } from "lucide-react";
import { api } from "@/lib/api";
import { Logo } from "@/components/walix/Logo";
import { LoadingSpinner } from "@/components/walix/LoadingSpinner";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

// ── Config shape ───────────────────────────────────────────────────────────────

interface BotPersona {
  name: string;
  system_prompt: string;
  tone?: string;
}

interface QualificationField {
  name: string;
  description: string | null;
}

interface Qualification {
  objective: string;
  criteria: string;
  disqualifiers: string;
  escalation_triggers: string;
  required_fields: QualificationField[];
}

interface StageSpec {
  name: string;
  slug: string;
  color: string | null;
  order_index: number;
  is_won: boolean;
  is_lost: boolean;
}

interface ChannelRules {
  max_chars: number;
  extra_rules?: string[];
}

interface GeneratedConfig {
  bot_persona: BotPersona;
  qualification: Qualification;
  pipeline_stages: StageSpec[];
  messages: Record<string, string>;
  channel_rules: ChannelRules;
}

// ── Section metadata ───────────────────────────────────────────────────────────

const SECTIONS = [
  { key: "bot_persona",     label: "🤖 Cómo responderá tu bot" },
  { key: "qualification",   label: "❓ Preguntas de calificación" },
  { key: "pipeline_stages", label: "📋 Etapas del pipeline" },
  { key: "messages",        label: "💬 Mensajes automáticos" },
  { key: "channel_rules",   label: "⚙️ Reglas del canal" },
] as const;

type SectionKey = (typeof SECTIONS)[number]["key"];

const MESSAGE_LABELS: Record<string, string> = {
  welcome_meta:       "Bienvenida (anuncio)",
  welcome_organic:    "Bienvenida orgánica",
  escalation:         "Escalado a agente",
  qualified:          "Lead calificado",
  disqualified:       "No califica",
  agent_notification: "Notificación al agente",
};

// ── Main component ─────────────────────────────────────────────────────────────

export default function PreviewPage() {
  const { draftId } = useParams<{ draftId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [editSection, setEditSection] = useState<SectionKey | null>(null);
  const [instruction, setInstruction] = useState("");
  const [showApprove, setShowApprove] = useState(false);

  const { data: draft, isLoading, isError } = useQuery({
    queryKey: ["draft", draftId],
    queryFn: () => api.getDraft(draftId!),
    enabled: !!draftId,
  });

  const refineMutation = useMutation({
    mutationFn: (vars: { section: string; instruction: string }) =>
      api.refineDraft({ draft_id: draftId!, section: vars.section, instruction: vars.instruction }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", draftId], updated);
      setEditSection(null);
      setInstruction("");
      toast.success("Sección actualizada");
    },
    onError: (e: Error) => toast.error("Error al refinar", { description: e.message }),
  });

  const approveMutation = useMutation({
    mutationFn: () => api.approveDraft(draftId!),
    onSuccess: () => {
      toast.success("¡Bot activado! Tu bot ya está listo.");
      navigate("/dashboard");
    },
    onError: (e: Error) => toast.error("Error al activar", { description: e.message }),
  });

  function openEdit(section: SectionKey) {
    setInstruction("");
    setEditSection(section);
  }

  const sectionLabel = SECTIONS.find((s) => s.key === editSection)?.label ?? "";

  if (isLoading) {
    return (
      <PageShell>
        <div className="flex-1 flex items-center justify-center">
          <LoadingSpinner />
        </div>
      </PageShell>
    );
  }

  if (isError || !draft) {
    return (
      <PageShell>
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-destructive">No se pudo cargar la configuración.</p>
        </div>
      </PageShell>
    );
  }

  const config = draft.generated_config as unknown as GeneratedConfig;
  const isApproved = draft.status === "approved";

  return (
    <PageShell>
      <main className="flex-1 py-10 px-4">
        <div className="w-full max-w-2xl mx-auto space-y-6">

          {/* Title */}
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold">Revisa la configuración de tu bot</h1>
              {isApproved && (
                <Badge className="bg-green-600 text-white">Activo</Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              Revisa cada sección. Si algo no está bien, usa el ícono de lápiz para ajustarlo.
            </p>
          </div>

          {/* Accordion */}
          <div className="rounded-2xl border bg-card shadow-sm overflow-hidden">
            <Accordion type="single" collapsible defaultValue="bot_persona">
              {SECTIONS.map((s) => (
                <AccordionItem
                  key={s.key}
                  value={s.key}
                  className="border-b last:border-b-0"
                >
                  <AccordionTrigger className="px-6 hover:bg-muted/30 hover:no-underline data-[state=open]:bg-muted/20">
                    <span className="font-semibold flex-1 text-left">{s.label}</span>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 shrink-0 mr-2 text-muted-foreground hover:text-foreground"
                      onClick={(e) => {
                        e.stopPropagation();
                        openEdit(s.key);
                      }}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                  </AccordionTrigger>
                  <AccordionContent className="px-6 pt-1 pb-5">
                    <SectionContent section={s.key} config={config} />
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>

          {/* Approve */}
          <Button
            size="lg"
            className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold"
            onClick={() => setShowApprove(true)}
            disabled={isApproved || approveMutation.isPending}
          >
            {isApproved ? "Configuración activada ✓" : "Activar configuración ✓"}
          </Button>
        </div>
      </main>

      {/* ── Edit dialog ── */}
      <Dialog open={!!editSection} onOpenChange={(open) => !open && setEditSection(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Editar: {sectionLabel}</DialogTitle>
          </DialogHeader>
          <Textarea
            rows={4}
            placeholder="Describe qué quieres cambiar en esta sección..."
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            disabled={refineMutation.isPending}
            className="resize-none"
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEditSection(null)}
              disabled={refineMutation.isPending}
            >
              Cancelar
            </Button>
            <Button
              disabled={!instruction.trim() || refineMutation.isPending}
              onClick={() =>
                refineMutation.mutate({ section: editSection!, instruction })
              }
            >
              {refineMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Aplicando...
                </>
              ) : (
                "Aplicar cambio"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Approve alert dialog ── */}
      <AlertDialog open={showApprove} onOpenChange={setShowApprove}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Estás seguro?</AlertDialogTitle>
            <AlertDialogDescription>
              Una vez activado, el bot empezará a responder leads con esta configuración.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={approveMutation.isPending}>
              Cancelar
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-green-600 hover:bg-green-700 focus:ring-green-600"
              disabled={approveMutation.isPending}
              onClick={() => approveMutation.mutate()}
            >
              {approveMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Activando...
                </>
              ) : (
                "Activar"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageShell>
  );
}

// ── Page shell ─────────────────────────────────────────────────────────────────

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-muted/30 flex flex-col">
      <header className="h-14 shrink-0 border-b bg-background flex items-center px-6">
        <Logo collapsed={false} />
      </header>
      {children}
    </div>
  );
}

// ── Section content ────────────────────────────────────────────────────────────

function SectionContent({
  section,
  config,
}: {
  section: SectionKey;
  config: GeneratedConfig;
}) {
  if (section === "bot_persona")
    return <BotPersonaSection persona={config.bot_persona} />;
  if (section === "qualification")
    return <QualificationSection qual={config.qualification} />;
  if (section === "pipeline_stages")
    return <PipelineSection stages={config.pipeline_stages ?? []} />;
  if (section === "messages")
    return <MessagesSection messages={config.messages ?? {}} />;
  if (section === "channel_rules")
    return <ChannelRulesSection rules={config.channel_rules} />;
  return null;
}

// ── Bot persona ────────────────────────────────────────────────────────────────

function BotPersonaSection({ persona }: { persona: BotPersona }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Badge variant="secondary" className="text-sm px-3 py-1">
          {persona.name}
        </Badge>
        {persona.tone && (
          <Badge variant="outline" className="text-sm px-3 py-1">
            {persona.tone}
          </Badge>
        )}
      </div>

      <div className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Prompt del sistema
        </p>
        <p
          className={cn(
            "text-sm whitespace-pre-wrap leading-relaxed text-foreground/80",
            !expanded && "line-clamp-3",
          )}
        >
          {persona.system_prompt}
        </p>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-xs text-primary hover:underline"
        >
          {expanded ? "ver menos" : "ver más"}
        </button>
      </div>
    </div>
  );
}

// ── Qualification ──────────────────────────────────────────────────────────────

function QualificationSection({ qual }: { qual: Qualification }) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Datos a recopilar
        </p>
        <div className="flex flex-wrap gap-2">
          {(qual.required_fields ?? []).map((f) => (
            <Badge key={f.name} variant="secondary" className="text-xs px-2.5 py-1">
              {f.name.replaceAll("_", " ")}
            </Badge>
          ))}
        </div>
      </div>

      <InfoCard label="Criterios de calificación" text={qual.criteria} />
      <InfoCard label="Descalificadores" text={qual.disqualifiers} />
    </div>
  );
}

function InfoCard({ label, text }: { label: string; text: string }) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</p>
      <div className="rounded-lg bg-muted px-3 py-2.5 text-sm text-foreground/80 leading-relaxed">
        {text}
      </div>
    </div>
  );
}

// ── Pipeline stages ────────────────────────────────────────────────────────────

function PipelineSection({ stages }: { stages: StageSpec[] }) {
  const sorted = [...stages].sort((a, b) => a.order_index - b.order_index);

  return (
    <div className="flex flex-wrap gap-2">
      {sorted.map((s) => (
        <div
          key={s.slug}
          className="flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium"
          style={{ borderColor: s.color ?? "#9B9893", color: s.color ?? "#9B9893" }}
        >
          {s.is_won && <Check className="h-3 w-3 text-green-600" strokeWidth={2.5} />}
          {s.is_lost && <X className="h-3 w-3 text-destructive" strokeWidth={2.5} />}
          {s.name}
        </div>
      ))}
    </div>
  );
}

// ── Messages ───────────────────────────────────────────────────────────────────

function MessagesSection({ messages }: { messages: Record<string, string> }) {
  const entries = Object.entries(messages);

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {entries.map(([key, value]) => (
        <div key={key} className="rounded-lg border bg-muted/40 p-3 space-y-1.5">
          <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
            {MESSAGE_LABELS[key] ?? key.replaceAll("_", " ")}
          </p>
          <p className="text-sm leading-relaxed">{value}</p>
        </div>
      ))}
    </div>
  );
}

// ── Channel rules ──────────────────────────────────────────────────────────────

function ChannelRulesSection({ rules }: { rules: ChannelRules }) {
  return (
    <div className="flex flex-wrap gap-2">
      <Badge variant="secondary" className="text-xs px-3 py-1">
        Máx. {rules.max_chars} caracteres
      </Badge>
      {(rules.extra_rules ?? []).map((r) => (
        <Badge key={r} variant="outline" className="text-xs px-3 py-1">
          {r}
        </Badge>
      ))}
    </div>
  );
}
