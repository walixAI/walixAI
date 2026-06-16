import { useState, useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { useAuthStore } from "@/store/auth";
import { api, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Logo } from "@/components/walix/Logo";
import {
  Loader2, UserPlus, MessageCircle, Bot, Zap, ShieldCheck,
  Eye, EyeOff, Building2, CheckCircle2, XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const REFERRAL_OPTIONS = [
  { value: "google",          label: "Google" },
  { value: "instagram",       label: "Instagram" },
  { value: "facebook",        label: "Facebook" },
  { value: "recomendacion",   label: "Recomendación" },
  { value: "otro",            label: "Otro" },
];

const schema = z.object({
  name:           z.string().trim().min(2, "Ingresa tu nombre completo"),
  email:          z.string().trim().min(1, "Ingresa tu correo").email("Correo inválido"),
  password:       z.string().min(8, "Mínimo 8 caracteres"),
  workspace_name: z.string().trim().min(2, "Ingresa el nombre de tu negocio"),
  phone:          z.string().optional(),
  referral_source:z.string().optional(),
});

type Field = "name" | "email" | "password" | "workspace_name" | "phone";

export default function Register() {
  const [form, setForm] = useState({
    name: "", email: "", password: "",
    workspace_name: "", phone: "", referral_source: "",
  });
  const [errors, setErrors]   = useState<Partial<Record<Field, string>>>({});
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  // Email availability check
  const [emailStatus, setEmailStatus] = useState<"idle" | "checking" | "available" | "taken">("idle");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const navigate = useNavigate();
  const { setUser, setTenant } = useAuthStore();

  // Debounced email check
  useEffect(() => {
    const email = form.email.trim();
    if (!email || !email.includes("@")) {
      setEmailStatus("idle");
      return;
    }
    setEmailStatus("checking");
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const { available } = await api.checkEmail(email);
        setEmailStatus(available ? "available" : "taken");
        if (!available) {
          setErrors((e) => ({ ...e, email: "Este correo ya tiene una cuenta" }));
        } else {
          setErrors((e) => ({ ...e, email: undefined }));
        }
      } catch {
        setEmailStatus("idle");
      }
    }, 500);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [form.email]);

  const set = (field: Field | "referral_source", value: string) => {
    setForm((f) => ({ ...f, [field]: value }));
    if (field !== "referral_source") {
      setErrors((e) => ({ ...e, [field as Field]: undefined }));
    }
  };

  const validate = (): boolean => {
    const result = schema.safeParse(form);
    if (!result.success) {
      const fieldErrors: Partial<Record<Field, string>> = {};
      for (const issue of result.error.issues) {
        const key = issue.path[0] as Field;
        if (!fieldErrors[key]) fieldErrors[key] = issue.message;
      }
      setErrors(fieldErrors);
      return false;
    }
    if (emailStatus === "taken") {
      setErrors((e) => ({ ...e, email: "Este correo ya tiene una cuenta" }));
      return false;
    }
    return true;
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    try {
      const { access_token, user } = await api.registerV2({
        name:            form.name.trim(),
        email:           form.email.trim(),
        password:        form.password,
        workspace_name:  form.workspace_name.trim(),
        phone:           form.phone.trim() || null,
        referral_source: form.referral_source || null,
      });
      setToken(access_token);
      const meData = await api.me();
      setUser(meData.user);
      setTenant(meData.tenant);
      toast.success("Cuenta creada", {
        description: `Bienvenido a Walix, ${user.name}. Configura tu industria.`,
      });
      navigate("/onboarding/new");
    } catch (err: any) {
      const msg = err?.message ?? "Error desconocido";
      if (msg.includes("409") || msg.toLowerCase().includes("registrado")) {
        toast.error("Correo ya registrado", { description: "Usa otro correo o inicia sesión." });
        setErrors({ email: "Este correo ya tiene una cuenta" });
      } else {
        toast.error("No se pudo crear la cuenta", { description: msg });
      }
    } finally {
      setLoading(false);
    }
  };

  const canSubmit =
    form.name.trim().length >= 2 &&
    form.email.trim().length > 0 &&
    form.password.length >= 8 &&
    form.workspace_name.trim().length >= 2 &&
    emailStatus !== "taken" &&
    emailStatus !== "checking";

  return (
    <div className="min-h-screen relative flex items-center justify-center p-4 overflow-hidden bg-gradient-soft">
      <div className="absolute inset-0 pointer-events-none opacity-40">
        <div className="absolute top-1/4 -left-20 w-[28rem] h-[28rem] rounded-full bg-primary/20 blur-3xl" />
        <div className="absolute bottom-0 -right-20 w-[28rem] h-[28rem] rounded-full bg-accent/20 blur-3xl" />
      </div>

      <div className="relative w-full max-w-[1040px] grid md:grid-cols-2 bg-card rounded-2xl shadow-2xl overflow-hidden animate-fade-in">
        {/* Panel izquierdo */}
        <aside className="hidden md:flex relative flex-col justify-between p-10 text-primary-foreground bg-gradient-hero overflow-hidden">
          <div className="absolute inset-0 opacity-40 pointer-events-none">
            <div className="absolute top-10 left-10 w-72 h-72 rounded-full bg-accent/40 blur-3xl" />
            <div className="absolute bottom-10 right-10 w-72 h-72 rounded-full bg-primary-glow/40 blur-3xl" />
          </div>

          <div className="relative"><Logo /></div>

          <div className="relative animate-fade-in space-y-6">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/10 backdrop-blur text-xs font-medium border border-white/15">
              <Building2 className="h-3.5 w-3.5" />
              14 días gratis · Sin tarjeta
            </span>
            <h1 className="text-3xl font-bold tracking-tight leading-tight">
              Tu negocio en WhatsApp, potenciado con IA
            </h1>
            <p className="text-sm text-primary-foreground/80 leading-relaxed">
              En menos de dos minutos tendrás tu CRM listo: califica leads, automatiza respuestas y cierra más ventas.
            </p>
            <ul className="space-y-3 pt-2">
              {[
                { icon: MessageCircle, text: "Atiende leads en WhatsApp 24/7" },
                { icon: Bot, text: "Agente IA configurado para tu industria" },
                { icon: Zap, text: "Pipeline y automatizaciones listas al instante" },
              ].map(({ icon: Icon, text }) => (
                <li key={text} className="flex items-center gap-3 text-sm">
                  <span className="grid place-items-center h-8 w-8 rounded-lg bg-white/10 border border-white/15">
                    <Icon className="h-4 w-4" />
                  </span>
                  {text}
                </li>
              ))}
            </ul>
          </div>

          <div className="relative flex items-center gap-2 text-[11px] text-primary-foreground/70">
            <ShieldCheck className="h-3.5 w-3.5" />
            Hecho en México · Datos cifrados
          </div>
        </aside>

        {/* Panel derecho: formulario */}
        <section className="relative p-6 sm:p-10 overflow-y-auto max-h-screen">
          <div className="flex md:hidden items-center justify-between mb-6">
            <Logo />
          </div>

          <div className="mb-5">
            <h2 className="text-2xl font-bold tracking-tight">Crea tu cuenta</h2>
            <p className="text-sm text-muted-foreground mt-1">
              14 días gratis, sin tarjeta de crédito.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            {/* Nombre */}
            <div className="space-y-1.5">
              <Label htmlFor="name">Tu nombre</Label>
              <Input
                id="name" type="text" autoComplete="name" required
                value={form.name} onChange={(e) => set("name", e.target.value)}
                placeholder="Ana López"
                aria-invalid={!!errors.name}
                className={cn("h-10", errors.name && "border-destructive focus-visible:ring-destructive")}
              />
              {errors.name && <p className="text-xs text-destructive">{errors.name}</p>}
            </div>

            {/* Nombre del negocio */}
            <div className="space-y-1.5">
              <Label htmlFor="workspace_name">Nombre de tu negocio</Label>
              <Input
                id="workspace_name" type="text" required
                value={form.workspace_name} onChange={(e) => set("workspace_name", e.target.value)}
                placeholder="Clínica Dr. Sánchez"
                aria-invalid={!!errors.workspace_name}
                className={cn("h-10", errors.workspace_name && "border-destructive focus-visible:ring-destructive")}
              />
              {errors.workspace_name && <p className="text-xs text-destructive">{errors.workspace_name}</p>}
            </div>

            {/* Email */}
            <div className="space-y-1.5">
              <Label htmlFor="email">Correo electrónico</Label>
              <div className="relative">
                <Input
                  id="email" type="email" autoComplete="email" required
                  value={form.email} onChange={(e) => set("email", e.target.value)}
                  placeholder="ana@clinica.mx"
                  aria-invalid={!!errors.email}
                  className={cn(
                    "h-10 pr-8",
                    errors.email && "border-destructive focus-visible:ring-destructive",
                    emailStatus === "available" && "border-green-500 focus-visible:ring-green-500",
                  )}
                />
                {emailStatus === "checking" && (
                  <Loader2 className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground animate-spin" />
                )}
                {emailStatus === "available" && (
                  <CheckCircle2 className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-green-500" />
                )}
                {emailStatus === "taken" && (
                  <XCircle className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-destructive" />
                )}
              </div>
              {emailStatus === "available" && (
                <p className="text-xs text-green-600">✓ Correo disponible</p>
              )}
              {errors.email && <p className="text-xs text-destructive">{errors.email}</p>}
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <Label htmlFor="password">Contraseña</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password" required
                  value={form.password} onChange={(e) => set("password", e.target.value)}
                  placeholder="Mínimo 8 caracteres"
                  aria-invalid={!!errors.password}
                  className={cn("h-10 pr-10", errors.password && "border-destructive focus-visible:ring-destructive")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                  className="absolute right-2 top-1/2 -translate-y-1/2 grid place-items-center h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {errors.password && <p className="text-xs text-destructive">{errors.password}</p>}
            </div>

            {/* Teléfono (opcional) */}
            <div className="space-y-1.5">
              <Label htmlFor="phone">
                Teléfono <span className="text-muted-foreground text-xs">(opcional)</span>
              </Label>
              <Input
                id="phone" type="tel" autoComplete="tel"
                value={form.phone} onChange={(e) => set("phone", e.target.value)}
                placeholder="+52 55 1234 5678"
                className="h-10"
              />
            </div>

            {/* ¿Cómo nos encontraste? */}
            <div className="space-y-1.5">
              <Label>
                ¿Cómo nos encontraste? <span className="text-muted-foreground text-xs">(opcional)</span>
              </Label>
              <Select
                value={form.referral_source}
                onValueChange={(v) => set("referral_source", v)}
              >
                <SelectTrigger className="h-10">
                  <SelectValue placeholder="Selecciona una opción" />
                </SelectTrigger>
                <SelectContent>
                  {REFERRAL_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Button
              type="submit"
              disabled={loading || !canSubmit}
              className="w-full h-11 bg-gradient-brand hover:opacity-90 text-primary-foreground font-semibold shadow-glow"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <UserPlus className="h-4 w-4 mr-2" />
              )}
              Crear cuenta gratis
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            ¿Ya tienes cuenta?{" "}
            <Link to="/login" className="font-medium text-primary hover:underline">
              Inicia sesión
            </Link>
          </p>
        </section>
      </div>
    </div>
  );
}
