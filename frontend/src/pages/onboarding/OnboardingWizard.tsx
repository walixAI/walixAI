/**
 * Sprint 8B — Onboarding conversacional.
 *
 * Flujo:
 *   1. Describe  — el usuario escribe libremente sobre su negocio
 *   2. Confirmar — Walix muestra la industria detectada + pipeline preview
 *   3. Aplicando — se aplica el template y se redirige al dashboard
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Logo } from "@/components/walix/Logo";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// ── Constantes (espejo de onboarding_guide.py) ────────────────────────────────

const SUGGESTED_TOPICS = [
  "El nombre de tu negocio o clínica",
  "A qué te dedicas y a quién atiendes",
  "Tu mayor problema con el seguimiento de clientes",
  "Cuántas personas atienden WhatsApp hoy",
];

const EXAMPLE_TEXT =
  'Ej: "Tengo una clínica de endocrinología pediátrica en Guadalajara. ' +
  "Atendemos a niños con problemas de tiroides y diabetes. Somos 2 médicos y una recepcionista. " +
  "El mayor problema es que los papás nos contactan por WhatsApp, agendamos la cita, " +
  'pero luego no vienen y no les damos seguimiento."';

const INDUSTRY_ICONS: Record<string, string> = {
  salud:                   "🏥",
  bienes_raices:           "🏠",
  educacion:               "📚",
  estetica_wellness:       "💆",
  automotriz:              "🚗",
  restaurante:             "🍽️",
  servicios_profesionales: "💼",
  generico:                "🏢",
};

const ALL_INDUSTRIES = [
  { key: "salud",                   label: "Clínica / Consultorio" },
  { key: "bienes_raices",           label: "Bienes Raíces" },
  { key: "educacion",               label: "Escuela / Academia" },
  { key: "estetica_wellness",       label: "Estética / Spa / Wellness" },
  { key: "automotriz",              label: "Taller / Agencia Automotriz" },
  { key: "restaurante",             label: "Restaurante / Food & Beverage" },
  { key: "servicios_profesionales", label: "Servicios Profesionales" },
  { key: "generico",                label: "Otro negocio" },
];

// ── Tipos del análisis ────────────────────────────────────────────────────────

interface AnalysisResult {
  session_id: string;
  industry_key: string;
  industry_label: string;
  entity_name: string;
  confidence: number;
  pipeline_preview: Array<{ key: string; label: string; order: number; color: string }>;
  reasoning: string;
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function OnboardingWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState<"describe" | "confirm" | "applying">("describe");

  // Estado step 1
  const [description, setDescription] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [followUpQuestions, setFollowUpQuestions] = useState<string[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // Estado step 2
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [selectedIndustry, setSelectedIndustry] = useState<string>("");
  const [overriding, setOverriding] = useState(false);

  // Estado step 3
  const [applyResult, setApplyResult] = useState<{
    message: string;
    entity_name: string;
    bot_config_generated: boolean;
    bot_config: { system_prompt: string; tone: string; qualification_questions: unknown[] } | null;
  } | null>(null);

  // ── Analizar ──────────────────────────────────────────────────────────────

  async function handleAnalyze() {
    if (!description.trim()) return;
    setIsAnalyzing(true);
    setFollowUpQuestions([]);
    try {
      const res = await api.analyzeIndustry({
        description: description.trim(),
        session_id: sessionId,
      });

      setSessionId(res.session_id);

      if (res.needs_more_info) {
        setFollowUpQuestions(res.follow_up_questions ?? []);
        if (res.hint) toast.info(res.hint);
        return;
      }

      if (res.industry_key && !res.needs_more_info) {
        setAnalysis({
          session_id: res.session_id,
          industry_key: res.industry_key,
          industry_label: res.industry_label ?? res.industry_key,
          entity_name: res.entity_name ?? "Contacto",
          confidence: res.confidence ?? 0,
          pipeline_preview: res.pipeline_preview ?? [],
          reasoning: res.reasoning ?? "",
        });
        setSelectedIndustry(res.industry_key);
        setStep("confirm");
      }
    } catch (e: unknown) {
      toast.error("No pudimos analizar tu descripción. Intenta de nuevo.");
    } finally {
      setIsAnalyzing(false);
    }
  }

  // ── Confirmar ─────────────────────────────────────────────────────────────

  const confirmMutation = useMutation({
    mutationFn: () =>
      api.confirmIndustry({
        description: description.trim(),
        industry_key: selectedIndustry,
        override_industry: selectedIndustry !== analysis?.industry_key,
      }),
    onSuccess: (data) => {
      setApplyResult({
        message: data.message,
        entity_name: data.entity_name,
        bot_config_generated: data.bot_config_generated ?? false,
        bot_config: data.bot_config ?? null,
      });
    },
    onError: () => {
      toast.error("Error al configurar. Intenta de nuevo.");
      setStep("confirm");
    },
  });

  function handleConfirm() {
    setStep("applying");
    confirmMutation.mutate();
  }

  // No auto-redirect — user clicks the button manually (see StepApplying)

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-muted/30 flex flex-col">
      <header className="h-14 shrink-0 border-b bg-background flex items-center px-6">
        <Logo collapsed={false} />
      </header>

      <main className="flex-1 flex items-center justify-center p-4 py-10">
        <div className="w-full max-w-lg space-y-5">

          {/* Progress */}
          <div className="space-y-1.5">
            <div className="flex gap-1.5">
              {(["describe", "confirm", "applying"] as const).map((s) => (
                <div
                  key={s}
                  className={cn(
                    "h-1.5 flex-1 rounded-full transition-colors duration-300",
                    stepIndex(s) <= stepIndex(step) ? "bg-primary" : "bg-muted",
                  )}
                />
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Paso {stepIndex(step)} de 3
            </p>
          </div>

          {/* Card */}
          <div className="rounded-2xl border bg-card shadow-sm p-6 sm:p-8">
            {step === "describe" && (
              <StepDescribe
                description={description}
                onDescriptionChange={setDescription}
                followUpQuestions={followUpQuestions}
                isAnalyzing={isAnalyzing}
                onAnalyze={handleAnalyze}
              />
            )}
            {step === "confirm" && analysis && (
              <StepConfirm
                analysis={analysis}
                selectedIndustry={selectedIndustry}
                overriding={overriding}
                onOverrideToggle={() => setOverriding((v) => !v)}
                onIndustryChange={(k) => setSelectedIndustry(k)}
                onBack={() => setStep("describe")}
                onConfirm={handleConfirm}
              />
            )}
            {step === "applying" && (
              <StepApplying
                result={applyResult}
                industryLabel={
                  ALL_INDUSTRIES.find((i) => i.key === selectedIndustry)?.label ?? selectedIndustry
                }
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

function stepIndex(s: "describe" | "confirm" | "applying") {
  return { describe: 1, confirm: 2, applying: 3 }[s];
}

// ── Step 1 — Describe ─────────────────────────────────────────────────────────

function StepDescribe({
  description,
  onDescriptionChange,
  followUpQuestions,
  isAnalyzing,
  onAnalyze,
}: {
  description: string;
  onDescriptionChange: (v: string) => void;
  followUpQuestions: string[];
  isAnalyzing: boolean;
  onAnalyze: () => void;
}) {
  const wordCount = description.trim().split(/\s+/).filter(Boolean).length;
  const canAnalyze = wordCount >= 10 && !isAnalyzing;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Cuéntanos
        </p>
        <h2 className="mt-1 text-xl font-semibold leading-snug">
          ¿Cómo es tu negocio?
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Descríbelo con tus propias palabras y Walix se configura solo.
        </p>
      </div>

      {/* Suggested topics */}
      <div className="flex items-start gap-2.5 rounded-xl bg-primary/5 border border-primary/10 p-3.5">
        <BookOpen className="h-4 w-4 text-primary shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="text-xs font-semibold text-primary">Incluye estos temas:</p>
          <ul className="space-y-0.5">
            {SUGGESTED_TOPICS.map((t) => (
              <li key={t} className="text-xs text-muted-foreground flex items-start gap-1.5">
                <span className="text-primary mt-0.5">·</span>{t}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Textarea */}
      <div className="space-y-1.5">
        <Textarea
          autoFocus
          rows={7}
          placeholder={EXAMPLE_TEXT}
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          className="resize-y text-sm"
        />
        <p className={cn(
          "text-[11px] text-right tabular-nums transition-colors",
          wordCount < 10 ? "text-muted-foreground" : "text-primary",
        )}>
          {wordCount} palabra{wordCount !== 1 ? "s" : ""}
          {wordCount < 20 && " — escribe un poco más para mejores resultados"}
        </p>
      </div>

      {/* Follow-up questions */}
      {followUpQuestions.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-2">
          <p className="text-xs font-semibold text-amber-800">
            Para afinar la configuración, cuéntanos:
          </p>
          <ul className="space-y-1">
            {followUpQuestions.map((q) => (
              <li key={q} className="text-sm text-amber-900 flex items-start gap-1.5">
                <ArrowRight className="h-3.5 w-3.5 shrink-0 mt-0.5 text-amber-600" />
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Button className="w-full gap-2" disabled={!canAnalyze} onClick={onAnalyze}>
        {isAnalyzing ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Analizando tu negocio…
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4" />
            Analizar mi negocio
          </>
        )}
      </Button>
    </div>
  );
}

// ── Step 2 — Confirmar ────────────────────────────────────────────────────────

function StepConfirm({
  analysis,
  selectedIndustry,
  overriding,
  onOverrideToggle,
  onIndustryChange,
  onBack,
  onConfirm,
}: {
  analysis: AnalysisResult;
  selectedIndustry: string;
  overriding: boolean;
  onOverrideToggle: () => void;
  onIndustryChange: (k: string) => void;
  onBack: () => void;
  onConfirm: () => void;
}) {
  const icon = INDUSTRY_ICONS[selectedIndustry] ?? "🏢";
  const confPct = Math.round((analysis.confidence ?? 0) * 100);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Listo
        </p>
        <h2 className="mt-1 text-xl font-semibold leading-snug">
          Industria detectada
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Revisa la configuración y confirma.
        </p>
      </div>

      {/* Industry card */}
      <div className="rounded-xl border-2 border-primary/30 bg-primary/5 p-5 space-y-3">
        <div className="flex items-center gap-3">
          <span className="text-4xl leading-none">{icon}</span>
          <div>
            <p className="text-lg font-bold leading-tight">
              {ALL_INDUSTRIES.find((i) => i.key === selectedIndustry)?.label ?? selectedIndustry}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <div className="h-1.5 w-20 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${confPct}%` }}
                />
              </div>
              <span className="text-xs text-muted-foreground">{confPct}% confianza</span>
            </div>
          </div>
        </div>
        {analysis.reasoning && (
          <p className="text-xs text-muted-foreground italic border-t border-border/50 pt-2">
            "{analysis.reasoning}"
          </p>
        )}
      </div>

      {/* Entity name */}
      <div className="flex items-center gap-2 text-sm">
        <CheckCircle2 className="h-4 w-4 text-primary shrink-0" />
        <span>
          Tus contactos se llamarán{" "}
          <strong>{analysis.entity_name}</strong>
        </span>
      </div>

      {/* Pipeline preview */}
      {analysis.pipeline_preview.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Pipeline de etapas
          </p>
          <div className="flex flex-wrap gap-1.5">
            {analysis.pipeline_preview.map((stage) => (
              <span
                key={stage.key}
                className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium text-white"
                style={{ backgroundColor: stage.color }}
              >
                {stage.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Override industry */}
      <div>
        <button
          type="button"
          onClick={onOverrideToggle}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronDown
            className={cn("h-3.5 w-3.5 transition-transform", overriding && "rotate-180")}
          />
          {overriding ? "Ocultar opciones" : "¿No es tu industria? Cámbiala"}
        </button>

        {overriding && (
          <div className="mt-2.5 grid grid-cols-2 gap-1.5">
            {ALL_INDUSTRIES.map((ind) => (
              <button
                key={ind.key}
                type="button"
                onClick={() => onIndustryChange(ind.key)}
                className={cn(
                  "flex items-center gap-2 rounded-lg border px-3 py-2 text-xs text-left transition-all",
                  selectedIndustry === ind.key
                    ? "border-primary bg-primary/5 font-semibold"
                    : "border-border hover:border-primary/40 hover:bg-muted/50",
                )}
              >
                <span>{INDUSTRY_ICONS[ind.key]}</span>
                <span className="truncate">{ind.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-3 pt-1">
        <Button variant="outline" className="flex-1" onClick={onBack}>
          Atrás
        </Button>
        <Button className="flex-1 gap-2" onClick={onConfirm}>
          <CheckCircle2 className="h-4 w-4" />
          Confirmar y activar
        </Button>
      </div>
    </div>
  );
}

// ── Step 3 — Applying ─────────────────────────────────────────────────────────

const TONE_LABELS: Record<string, string> = {
  amigable:    "😊 Amigable",
  profesional: "💼 Profesional",
  formal:      "🎯 Formal",
  cercano:     "🤝 Cercano",
};

function StepApplying({
  result,
  industryLabel,
}: {
  result: {
    message: string;
    entity_name: string;
    bot_config_generated: boolean;
    bot_config: { system_prompt: string; tone: string; qualification_questions: Array<{ order: number; question: string; field_key: string }> } | null;
  } | null;
  industryLabel: string;
}) {
  const navigate = useNavigate();
  const [botExpanded, setBotExpanded] = useState(false);

  if (result) {
    const bc = result.bot_config;
    return (
      <div className="space-y-6 py-4">
        {/* Success header */}
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
            <CheckCircle2 className="h-8 w-8 text-primary" />
          </div>
          <h2 className="text-xl font-semibold">¡Tu workspace está listo!</h2>
          <p className="text-sm text-muted-foreground">{result.message}</p>
        </div>

        {/* Bot config result */}
        {result.bot_config_generated && bc ? (
          <div className="rounded-xl border border-border bg-muted/30 overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-left"
              onClick={() => setBotExpanded((v) => !v)}
            >
              <span className="flex items-center gap-2 text-success">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                Tu bot ya está configurado
              </span>
              <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", botExpanded && "rotate-180")} />
            </button>
            {botExpanded && (
              <div className="px-4 pb-4 space-y-3 border-t border-border">
                {/* Tono */}
                <div className="flex items-center gap-2 pt-3">
                  <span className="text-xs text-muted-foreground">Tono:</span>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                    {TONE_LABELS[bc.tone] ?? bc.tone}
                  </span>
                </div>
                {/* Preguntas */}
                {bc.qualification_questions.length > 0 && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1.5">Preguntas de calificación:</p>
                    <ol className="space-y-1">
                      {bc.qualification_questions.map((q, i) => (
                        <li key={i} className="text-xs text-foreground flex gap-2">
                          <span className="text-muted-foreground shrink-0">{q.order}.</span>
                          <span>{q.question}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
                {/* Primer párrafo del system prompt */}
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Vista previa del sistema:</p>
                  <p className="text-xs text-foreground/80 bg-background rounded p-2 leading-relaxed line-clamp-3">
                    {bc.system_prompt.split("\n")[0]}
                  </p>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-xl border border-warning/30 bg-warning/5 px-4 py-3 flex items-start gap-2">
            <span className="text-warning mt-0.5">⚠️</span>
            <p className="text-sm text-warning">
              No pudimos configurar tu bot automáticamente.
              Puedes hacerlo en <span className="font-semibold">Configuración → Bot</span>.
            </p>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex flex-col gap-2">
          <Button className="w-full gap-2" onClick={() => navigate("/dashboard")}>
            Ir al Dashboard
            <ArrowRight className="h-4 w-4" />
          </Button>
          {result.bot_config_generated && (
            <Button
              variant="outline"
              className="w-full gap-2"
              onClick={() => navigate("/settings?tab=bot")}
            >
              <BookOpen className="h-4 w-4" />
              Ajustar configuración del bot
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-6 py-10 text-center">
      <Loader2 className="h-14 w-14 animate-spin text-primary" />
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">Configurando tu Walix…</h2>
        <p className="text-sm text-muted-foreground">
          Creando el pipeline para{" "}
          <span className="font-medium text-foreground">{industryLabel}</span>
        </p>
        <p className="text-xs text-muted-foreground">
          Generando la configuración inicial del bot con IA…
        </p>
      </div>
    </div>
  );
}
