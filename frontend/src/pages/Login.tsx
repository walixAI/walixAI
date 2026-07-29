import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { useAuthStore } from "@/stores/auth";
import { api, setToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/walix/Logo";
import {
  Loader2,
  LogIn,
  MessageCircle,
  Bot,
  Zap,
  ShieldCheck,
  Eye,
  EyeOff,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const emailSchema = z
  .string()
  .trim()
  .min(1, "Ingresa tu correo electronico")
  .max(255, "El correo es demasiado largo")
  .email("Correo electronico invalido");

function validateEmail(email: string): string | null {
  const parsed = emailSchema.safeParse(email);
  if (!parsed.success) return parsed.error.issues[0].message;
  return null;
}

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { setUser, setTenant } = useAuthStore();

  const canSubmit = email.trim().length > 0 && password.length > 0;

  const handleEmailBlur = () => {
    if (!email) return;
    setEmailError(validateEmail(email));
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const emailErr = validateEmail(email);
    if (emailErr) {
      setEmailError(emailErr);
      toast.error("Revisa tu correo", { description: emailErr });
      return;
    }

    setLoading(true);
    try {
      const { access_token, user } = await api.login(email.trim(), password);
      setToken(access_token);
      const meData = await api.me();
      setUser(meData.user);
      setTenant(meData.tenant);
      toast.success("Bienvenido, " + user.name);
      navigate(user.role === "platform_owner" ? "/platform" : "/dashboard");
    } catch (err: any) {
      const msg = err?.message ?? "Error desconocido";
      if (msg.toLowerCase().includes("401") || msg.toLowerCase().includes("incorrect") || msg.toLowerCase().includes("invalid")) {
        toast.error("Credenciales incorrectas", {
          description: "El correo o la contrasena no coinciden.",
        });
      } else {
        toast.error("No se pudo iniciar sesion", { description: msg });
      }
    } finally {
      setLoading(false);
    }
  };

  const leftPanel = {
    eyebrow: "Bienvenido de vuelta",
    title: "Continua donde lo dejaste",
    subtitle: "Tus conversaciones, oportunidades y automatizaciones te esperan.",
    bullets: [
      { icon: MessageCircle, text: "Tus conversaciones siguen vivas" },
      { icon: Zap, text: "Tus leads y calificaciones, al dia" },
      { icon: Bot, text: "IA lista para asistirte" },
    ],
  };

  return (
    <div className="min-h-screen relative flex items-center justify-center p-4 overflow-hidden bg-gradient-soft">
      <div className="absolute inset-0 pointer-events-none opacity-40">
        <div className="absolute top-1/4 -left-20 w-[28rem] h-[28rem] rounded-full bg-primary/20 blur-3xl" />
        <div className="absolute bottom-0 -right-20 w-[28rem] h-[28rem] rounded-full bg-accent/20 blur-3xl" />
      </div>

      <div className="relative w-full max-w-[1040px] grid md:grid-cols-2 bg-card rounded-2xl shadow-2xl overflow-hidden animate-fade-in">
        {/* Panel izquierdo: branding */}
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
              <LogIn className="h-3.5 w-3.5" />
              {leftPanel.eyebrow}
            </span>
            <h1 className="text-3xl font-bold tracking-tight leading-tight">
              {leftPanel.title}
            </h1>
            <p className="text-sm text-primary-foreground/80 leading-relaxed">
              {leftPanel.subtitle}
            </p>

            <ul className="space-y-3 pt-2">
              {leftPanel.bullets.map(({ icon: Icon, text }) => (
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
          {/* Mini-header en movil */}
          <div className="flex md:hidden items-center justify-between mb-6">
            <Logo />
          </div>

          {/* Header */}
          <div className="mb-6">
            <h2 className="text-2xl font-bold tracking-tight">Inicia sesion</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Accede a tu workspace de Walix.ai.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="email">Correo electronico</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (emailError) setEmailError(null);
                }}
                onBlur={handleEmailBlur}
                placeholder="tu@empresa.mx"
                aria-invalid={!!emailError}
                aria-describedby={emailError ? "email-error" : undefined}
                className={cn("h-11", emailError && "border-destructive focus-visible:ring-destructive")}
              />
              {emailError && (
                <p id="email-error" className="text-xs text-destructive mt-1">
                  {emailError}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">Contraseña</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="h-11 pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Ocultar" : "Mostrar"}
                  aria-pressed={showPassword}
                  className="absolute right-2 top-1/2 -translate-y-1/2 grid place-items-center h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  tabIndex={0}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading || !canSubmit}
              className="w-full h-11 bg-gradient-brand hover:opacity-90 text-primary-foreground font-semibold shadow-glow"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <LogIn className="h-4 w-4 mr-2" />
              )}
              Entrar
            </Button>
          </form>

          <p className="mt-5 text-center text-sm text-muted-foreground">
            No tienes cuenta?{" "}
            <Link
              to="/register"
              className="font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
            >
              Crea tu workspace
            </Link>
          </p>
        </section>
      </div>
    </div>
  );
}
