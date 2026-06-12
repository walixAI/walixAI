import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { useAuthStore } from "@/store/auth";
import { api, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/walix/Logo";
import {
  Loader2,
  UserPlus,
  MessageCircle,
  Bot,
  Zap,
  ShieldCheck,
  Eye,
  EyeOff,
  Building2,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const schema = z.object({
  name: z.string().trim().min(2, "Ingresa tu nombre completo"),
  email: z
    .string()
    .trim()
    .min(1, "Ingresa tu correo electronico")
    .email("Correo electronico invalido"),
  password: z.string().min(8, "La contrasena debe tener al menos 8 caracteres"),
});

type Field = "name" | "email" | "password";

export default function Register() {
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);

  const set = (field: Field, value: string) => {
    setForm((f) => ({ ...f, [field]: value }));
    setErrors((e) => ({ ...e, [field]: undefined }));
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
    return true;
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    try {
      const { access_token, user } = await api.register({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
      });
      setToken(access_token);
      setUser(user);
      toast.success("Cuenta creada", {
        description: `Bienvenido a Walix, ${user.name}. Ahora configura tu workspace.`,
      });
      navigate(`/onboarding/new?branch_id=${user.branch_id}`);
    } catch (err: any) {
      const msg = err?.message ?? "Error desconocido";
      if (msg.includes("409") || msg.toLowerCase().includes("registrado")) {
        toast.error("Correo ya registrado", {
          description: "Usa otro correo o inicia sesion.",
        });
        setErrors({ email: "Este correo ya esta registrado" });
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
    form.password.length >= 8;

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

          <div className="relative">
            <Logo />
          </div>

          <div className="relative animate-fade-in space-y-6">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/10 backdrop-blur text-xs font-medium border border-white/15">
              <Building2 className="h-3.5 w-3.5" />
              Crea tu workspace
            </span>
            <h1 className="text-3xl font-bold tracking-tight leading-tight">
              Tu negocio en WhatsApp, potenciado con IA
            </h1>
            <p className="text-sm text-primary-foreground/80 leading-relaxed">
              En menos de dos minutos tendras tu ambiente listo: califica leads, automatiza respuestas y cierra mas ventas.
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
            Hecho en Mexico · Datos cifrados
          </div>
        </aside>

        {/* Panel derecho: formulario */}
        <section className="relative p-6 sm:p-10">
          <div className="flex md:hidden items-center justify-between mb-6">
            <Logo />
          </div>

          <div className="mb-6">
            <h2 className="text-2xl font-bold tracking-tight">Crea tu cuenta</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Solo necesitas tu nombre, correo y contrasena. Configuraremos tu workspace en el siguiente paso.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="name">Tu nombre</Label>
              <Input
                id="name"
                type="text"
                autoComplete="name"
                required
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="Ana Lopez"
                aria-invalid={!!errors.name}
                className={cn("h-11", errors.name && "border-destructive focus-visible:ring-destructive")}
              />
              {errors.name && (
                <p className="text-xs text-destructive">{errors.name}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="email">Correo electronico</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
                placeholder="ana@empresa.mx"
                aria-invalid={!!errors.email}
                className={cn("h-11", errors.email && "border-destructive focus-visible:ring-destructive")}
              />
              {errors.email && (
                <p className="text-xs text-destructive">{errors.email}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">Contrasena</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  required
                  value={form.password}
                  onChange={(e) => set("password", e.target.value)}
                  placeholder="Minimo 8 caracteres"
                  aria-invalid={!!errors.password}
                  className={cn(
                    "h-11 pr-10",
                    errors.password && "border-destructive focus-visible:ring-destructive",
                  )}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Ocultar contrasena" : "Mostrar contrasena"}
                  aria-pressed={showPassword}
                  className="absolute right-2 top-1/2 -translate-y-1/2 grid place-items-center h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  tabIndex={0}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {errors.password && (
                <p className="text-xs text-destructive">{errors.password}</p>
              )}
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
              Continuar
            </Button>
          </form>

          <p className="mt-5 text-center text-sm text-muted-foreground">
            Ya tienes cuenta?{" "}
            <Link
              to="/login"
              className="font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
            >
              Inicia sesion
            </Link>
          </p>
        </section>
      </div>
    </div>
  );
}
