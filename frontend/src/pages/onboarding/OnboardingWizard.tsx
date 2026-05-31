import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Logo } from "@/components/walix/Logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

// ── Constants ──────────────────────────────────────────────────────────────────

const INDUSTRIES = [
  { id: "salud",        label: "Salud",             emoji: "🏥", hint: "Clínicas, consultorios, hospitales" },
  { id: "inmobiliaria", label: "Inmobiliaria",       emoji: "🏠", hint: "Venta y renta de propiedades" },
  { id: "educacion",    label: "Educación",          emoji: "📚", hint: "Escuelas, cursos, capacitación" },
  { id: "fintech",      label: "Fintech / Seguros",  emoji: "💰", hint: "Créditos, inversión, seguros" },
] as const;

const LOADING_TEXTS = [
  "Analizando tu negocio...",
  "Generando criterios de calificación...",
  "Creando el pipeline...",
  "Configurando mensajes...",
];

const MIN_DESC_CHARS = 80;

// ── Root component ─────────────────────────────────────────────────────────────

export default function OnboardingWizard() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const branchId = searchParams.get("branch_id") ?? "";

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [industry, setIndustry] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [description, setDescription] = useState("");
  const [loadingIdx, setLoadingIdx] = useState(0);

  const mutation = useMutation({
    mutationFn: () =>
      api.generateOnboarding({
        branch_id: branchId,
        business_description: [businessName.trim(), description.trim()]
          .filter(Boolean)
          .join("\n\n"),
        industry,
      }),
    onSuccess: (draft) => {
      navigate(`/onboarding/preview/${draft.id}`);
    },
  });

  // Cycle loading text while the API call is in-flight
  useEffect(() => {
    if (step !== 3 || !mutation.isPending) return;
    setLoadingIdx(0);
    const id = setInterval(
      () => setLoadingIdx((i) => (i + 1) % LOADING_TEXTS.length),
      2000,
    );
    return () => clearInterval(id);
  }, [step, mutation.isPending]);

  function goToStep3() {
    setStep(3);
    mutation.mutate();
  }

  function handleRetry() {
    mutation.reset();
    setStep(2);
  }

  return (
    <div className="min-h-screen bg-muted/30 flex flex-col">
      {/* Page header */}
      <header className="h-14 shrink-0 border-b bg-background flex items-center px-6">
        <Logo collapsed={false} />
      </header>

      {/* Centered content */}
      <main className="flex-1 flex items-center justify-center p-4 py-10">
        <div className="w-full max-w-lg space-y-5">

          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="flex gap-1.5">
              {([1, 2, 3] as const).map((s) => (
                <div
                  key={s}
                  className={cn(
                    "h-1.5 flex-1 rounded-full transition-colors duration-300",
                    s <= step ? "bg-primary" : "bg-muted",
                  )}
                />
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Paso {step} de 3
            </p>
          </div>

          {/* Step card */}
          <div className="rounded-2xl border bg-card shadow-sm p-6 sm:p-8">
            {step === 1 && (
              <Step1
                industry={industry}
                businessName={businessName}
                onIndustryChange={setIndustry}
                onBusinessNameChange={setBusinessName}
                onNext={() => setStep(2)}
              />
            )}
            {step === 2 && (
              <Step2
                description={description}
                onChange={setDescription}
                onBack={() => setStep(1)}
                onGenerate={goToStep3}
              />
            )}
            {step === 3 && (
              <Step3
                loadingText={LOADING_TEXTS[loadingIdx]}
                isLoading={mutation.isPending}
                error={mutation.error?.message ?? null}
                onRetry={handleRetry}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

// ── Step 1 — Industry + business name ─────────────────────────────────────────

function Step1({
  industry,
  businessName,
  onIndustryChange,
  onBusinessNameChange,
  onNext,
}: {
  industry: string;
  businessName: string;
  onIndustryChange: (v: string) => void;
  onBusinessNameChange: (v: string) => void;
  onNext: () => void;
}) {
  const canContinue = !!industry && businessName.trim().length > 0;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Empecemos
        </p>
        <h2 className="mt-1 text-xl font-semibold leading-snug">
          ¿Qué tipo de negocio tienes?
        </h2>
      </div>

      {/* Industry grid */}
      <div className="grid grid-cols-2 gap-3">
        {INDUSTRIES.map((ind) => (
          <button
            key={ind.id}
            type="button"
            onClick={() => onIndustryChange(ind.id)}
            className={cn(
              "flex flex-col items-center gap-2 rounded-xl border-2 p-4 text-center",
              "transition-all duration-150 hover:border-primary/50 hover:bg-primary/5",
              industry === ind.id
                ? "border-primary bg-primary/5 shadow-sm"
                : "border-border bg-background",
            )}
          >
            <span className="text-3xl leading-none" aria-hidden="true">
              {ind.emoji}
            </span>
            <span className="text-sm font-semibold leading-tight">{ind.label}</span>
            <span className="text-[11px] text-muted-foreground leading-snug">
              {ind.hint}
            </span>
          </button>
        ))}
      </div>

      {/* Business name */}
      <div className="space-y-1.5">
        <Label htmlFor="business-name">¿Cómo se llama tu empresa?</Label>
        <Input
          id="business-name"
          placeholder="Ej. Clínica EndoPed Monterrey"
          value={businessName}
          onChange={(e) => onBusinessNameChange(e.target.value)}
        />
      </div>

      <Button className="w-full" disabled={!canContinue} onClick={onNext}>
        Continuar
      </Button>
    </div>
  );
}

// ── Step 2 — Business description ─────────────────────────────────────────────

function Step2({
  description,
  onChange,
  onBack,
  onGenerate,
}: {
  description: string;
  onChange: (v: string) => void;
  onBack: () => void;
  onGenerate: () => void;
}) {
  const charCount = description.trim().length;
  const canGenerate = charCount >= MIN_DESC_CHARS;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Paso 2
        </p>
        <h2 className="mt-1 text-xl font-semibold leading-snug">
          Cuéntanos sobre tu negocio
        </h2>
      </div>

      <div className="space-y-2">
        <Textarea
          rows={6}
          placeholder="Describe qué vendes o ofreces, a quién le vendes y qué tipo de cliente o lead quieres que Walix califique automáticamente. Entre más detalle, mejor configurará el sistema."
          value={description}
          onChange={(e) => onChange(e.target.value)}
          className="resize-none"
        />

        <div className="flex items-start justify-between gap-3">
          <p className="text-[11px] text-muted-foreground leading-relaxed italic">
            Ejemplo: Somos una inmobiliaria en Monterrey. Vendemos casas de 1.5 a
            8 millones de pesos a familias que buscan primera vivienda...
          </p>
          <span
            className={cn(
              "text-xs tabular-nums shrink-0 font-medium",
              canGenerate ? "text-success" : "text-muted-foreground",
            )}
          >
            {charCount}/{MIN_DESC_CHARS}
          </span>
        </div>
      </div>

      <div className="flex gap-3">
        <Button variant="outline" className="flex-1" onClick={onBack}>
          Atrás
        </Button>
        <Button className="flex-1" disabled={!canGenerate} onClick={onGenerate}>
          Generar configuración
        </Button>
      </div>
    </div>
  );
}

// ── Step 3 — Generating / error ────────────────────────────────────────────────

function Step3({
  loadingText,
  isLoading,
  error,
  onRetry,
}: {
  loadingText: string;
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (error) {
    return (
      <div className="flex flex-col items-center gap-5 py-6 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">Algo salió mal</h2>
          <p className="text-sm text-muted-foreground max-w-xs mx-auto">{error}</p>
        </div>
        <Button className="w-full" onClick={onRetry}>
          Intentar de nuevo
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-6 py-8 text-center">
      <Loader2 className="h-16 w-16 animate-spin text-primary" />
      <div className="space-y-2">
        <h2 className="text-xl font-semibold">Configurando tu bot...</h2>
        <p
          key={loadingText}
          className="text-sm text-muted-foreground animate-fade-in"
        >
          {isLoading ? loadingText : "Finalizando..."}
        </p>
      </div>
    </div>
  );
}
