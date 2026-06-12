import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
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

const SECONDARY_INDUSTRIES = [
  { id: "restaurantes",  label: "Restaurantes",   emoji: "🍽️" },
  { id: "automotriz",    label: "Automotriz",      emoji: "🚗" },
  { id: "construccion",  label: "Construcción",    emoji: "🔨" },
  { id: "legal",         label: "Legal",           emoji: "⚖️" },
  { id: "belleza",       label: "Belleza / Spa",   emoji: "💄" },
  { id: "logistica",     label: "Logística",       emoji: "🚚" },
] as const;

const ALL_PRESET_IDS = [
  ...INDUSTRIES.map((i) => i.id),
  ...SECONDARY_INDUSTRIES.map((i) => i.id),
] as string[];

const LOADING_TEXTS = [
  "Analizando tu negocio...",
  "Generando criterios de calificación...",
  "Creando el pipeline...",
  "Configurando mensajes...",
];

const INDUSTRY_EXAMPLES: Record<string, { title: string; text: string }[]> = {
  salud: [
    {
      title: "Clínica de especialidad",
      text: "Somos una clínica de endocrinología pediátrica en Monterrey. Atendemos niños de 0 a 18 años con problemas de diabetes, obesidad y talla baja. Nuestros leads llegan por Meta Ads. Queremos calificar si el paciente es menor de edad, si tiene diagnóstico previo, si el padre o tutor puede agendar cita esta semana y si cuenta con seguro médico o paga de contado.",
    },
    {
      title: "Consultorio dental",
      text: "Somos un consultorio dental en CDMX. Ofrecemos ortodoncia, implantes y limpieza. Nuestros pacientes son adultos de 20 a 55 años. Queremos saber si el lead tiene dolor activo, qué tratamiento le interesa, si tiene seguro dental y cuándo puede agendar su primera consulta.",
    },
  ],
  inmobiliaria: [
    {
      title: "Venta residencial",
      text: "Somos una inmobiliaria en Monterrey. Vendemos casas residenciales de 1.5 a 8 millones de pesos a familias que buscan primera vivienda o inversión. Queremos calificar si el lead ya tiene preaprobación de crédito hipotecario, su rango de presupuesto, la zona de interés y si puede visitar una propiedad esta semana.",
    },
    {
      title: "Renta de oficinas",
      text: "Rentamos espacios de oficina y coworking en Santa Fe, CDMX. Nuestros clientes son startups y empresas medianas. Queremos saber el número de personas, el plazo de renta requerido, si necesitan sala de juntas privada y cuándo quieren iniciar.",
    },
  ],
  educacion: [
    {
      title: "Escuela de idiomas",
      text: "Somos una escuela de inglés en línea para adultos trabajadores. Ofrecemos cursos de nivel básico a avanzado con clases en vivo dos veces por semana. Queremos calificar si el prospecto trabaja actualmente, su nivel actual de inglés, si busca inglés de negocios o conversacional y si puede iniciar este mes.",
    },
    {
      title: "Cursos de capacitación",
      text: "Ofrecemos diplomados en marketing digital y ventas para profesionales en México. Nuestros cursos duran 3 meses y son en línea. Queremos saber si el prospecto trabaja en el área, qué habilidad quiere desarrollar, si su empresa subsidia la capacitación y si puede inscribirse en la siguiente cohorte.",
    },
  ],
  fintech: [
    {
      title: "Créditos personales",
      text: "Somos una financiera que otorga créditos personales de 5,000 a 100,000 pesos en 24 horas. Atendemos empleados formales y microempresarios en todo México. Queremos calificar si tiene empleo formal o negocio propio, el monto que necesita, para qué lo usará y si tiene historial crediticio.",
    },
    {
      title: "Seguros",
      text: "Vendemos seguros de gastos médicos mayores y de vida para familias y empresas en México. Queremos calificar si el lead ya tiene seguro actual, cuántas personas cubriría la póliza, el rango de edad de los asegurados y si tiene presupuesto mensual definido.",
    },
  ],
  otro: [
    {
      title: "Ejemplo genérico",
      text: "Describe qué vendes o servicios que ofreces, a quién va dirigido (perfil del cliente ideal), de dónde vienen tus leads y qué información necesitas recopilar para saber si un prospecto vale la pena atender. Entre más detalle incluyas, mejor configurará el sistema el bot, el pipeline y los criterios de calificación.",
    },
  ],
};

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
  const [prefilled, setPrefilled] = useState(false);

  const { data: existing } = useQuery({
    queryKey: ["bot-config", branchId],
    queryFn: () => api.getBotConfig(branchId),
    enabled: !!branchId,
  });

  // Pre-populate fields once the existing config loads
  useEffect(() => {
    if (!existing || prefilled) return;
    if (existing.industry) setIndustry(existing.industry);
    if (existing.branch_name) setBusinessName(existing.branch_name);
    if (existing.business_description) setDescription(existing.business_description);
    setPrefilled(true);
  }, [existing, prefilled]);

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
                industry={industry}
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
  // Local state for the free-text input; initialized from prop if it was a custom value
  const [customInput, setCustomInput] = useState(() =>
    ALL_PRESET_IDS.includes(industry) ? "" : industry,
  );

  const handlePresetSelect = (id: string) => {
    setCustomInput("");
    onIndustryChange(id);
  };

  const handleCustomChange = (v: string) => {
    setCustomInput(v);
    onIndustryChange(v.trim());
  };

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

      {/* Primary industry grid */}
      <div className="grid grid-cols-2 gap-3">
        {INDUSTRIES.map((ind) => (
          <button
            key={ind.id}
            type="button"
            onClick={() => handlePresetSelect(ind.id)}
            className={cn(
              "flex flex-col items-center gap-2 rounded-xl border-2 p-4 text-center",
              "transition-all duration-150 hover:border-primary/50 hover:bg-primary/5",
              industry === ind.id && !customInput
                ? "border-primary bg-primary/5 shadow-sm"
                : "border-border bg-background",
            )}
          >
            <span className="text-3xl leading-none" aria-hidden="true">{ind.emoji}</span>
            <span className="text-sm font-semibold leading-tight">{ind.label}</span>
            <span className="text-[11px] text-muted-foreground leading-snug">{ind.hint}</span>
          </button>
        ))}
      </div>

      {/* Secondary industries */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">Más industrias</p>
        <div className="flex flex-wrap gap-2">
          {SECONDARY_INDUSTRIES.map((ind) => (
            <button
              key={ind.id}
              type="button"
              onClick={() => handlePresetSelect(ind.id)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium",
                "transition-all duration-150 hover:border-primary/50 hover:bg-primary/5",
                industry === ind.id && !customInput
                  ? "border-primary bg-primary/5 text-primary"
                  : "border-border bg-background text-foreground",
              )}
            >
              <span aria-hidden="true">{ind.emoji}</span>
              {ind.label}
            </button>
          ))}
        </div>
      </div>

      {/* Custom industry */}
      <div className="space-y-1.5">
        <Label htmlFor="custom-industry">O escribe tu industria</Label>
        <Input
          id="custom-industry"
          placeholder="Ej. Agencia de viajes, Veterinaria..."
          value={customInput}
          onChange={(e) => handleCustomChange(e.target.value)}
          className={cn(customInput && "border-primary ring-1 ring-primary/30")}
        />
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
  industry,
  onChange,
  onBack,
  onGenerate,
}: {
  description: string;
  industry: string;
  onChange: (v: string) => void;
  onBack: () => void;
  onGenerate: () => void;
}) {
  const canGenerate = description.trim().length > 0;
  const examples = INDUSTRY_EXAMPLES[industry] ?? INDUSTRY_EXAMPLES.otro;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Paso 2
        </p>
        <h2 className="mt-1 text-xl font-semibold leading-snug">
          Cuéntanos sobre tu negocio
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Describe qué ofreces, a quién y qué información necesitas de cada lead para calificarlo.
        </p>
      </div>

      <Textarea
        rows={7}
        placeholder="Escribe aquí la descripción de tu negocio..."
        value={description}
        onChange={(e) => onChange(e.target.value)}
        className="resize-y"
      />

      {/* Industry examples */}
      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Ejemplos para tu industria
        </p>
        <div className="space-y-2">
          {examples.map((ex) => (
            <div
              key={ex.title}
              className="rounded-lg border border-border bg-muted/40 p-3 space-y-2"
            >
              <p className="text-xs font-semibold text-foreground">{ex.title}</p>
              <p className="text-[11px] text-muted-foreground leading-relaxed">{ex.text}</p>
              <button
                type="button"
                onClick={() => onChange(ex.text)}
                className="text-[11px] font-medium text-primary hover:underline focus-visible:outline-none"
              >
                Usar como base
              </button>
            </div>
          ))}
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
