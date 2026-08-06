import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, LogOut, User as UserIcon, Loader2, MapPin, Sparkles } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/hooks/useAuth";
import { clearToken, api } from "@/lib/api";
import { useAIBarStore } from "@/stores/aiBarStore";
import { AIPanel } from "@/components/ai/AIPanel";
import { useCopilotStore } from "@/stores/copilot";
import { cn } from "@/lib/utils";

export function TopBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const initials = (user?.name ?? user?.email ?? "U")
    .split(" ")
    .map((s: string) => s[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const signOut = () => {
    clearToken();
    logout();
    navigate("/login");
  };

  // ── Walix AI ─────────────────────────────────────────────────────────────
  const {
    isOpen,
    history,
    currentContext,
    isLoading,
    draftInput,
    pendingSuggestionsCount,
    setOpen,
    addMessage,
    setLoading,
    setDraftInput,
  } = useAIBarStore();

  const [inputValue, setInputValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (draftInput) {
      setInputValue(draftInput);
      setDraftInput("");
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [draftInput, setDraftInput]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === "Escape") inputRef.current?.blur();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Derive contact_id from current URL for context-aware commands
  const pathname = window.location.pathname;
  const contactIdFromUrl = (() => {
    const m = pathname.match(/^\/contacts\/([0-9a-f-]{36})/i);
    return m ? m[1] : undefined;
  })();

  const mutation = useMutation({
    mutationFn: api.sendAICommand,
    retry: 1,
    onSuccess: (data) => {
      addMessage("assistant", data.response_text, data.suggested_actions, data.action_data);
      setLoading(false);
    },
    onError: (err: Error) => {
      const detail = err?.message ?? "desconocido";
      addMessage("assistant", `Error: ${detail}`, [], null);
      setLoading(false);
    },
  });

  const { pendingCommand, setPendingCommand } = useAIBarStore();
  const openCopilot = useCopilotStore((s) => s.openDrawer);

  const buildCtx = (extra?: Record<string, unknown>): Record<string, unknown> => ({
    ...currentContext,
    // Normalize: contact detail pages use screen="lead" so enrich_context() activates _enrich_lead()
    screen: contactIdFromUrl ? "lead" : pathname.replace(/^\//, ""),
    ...(contactIdFromUrl ? { lead_id: contactIdFromUrl } : {}),
    ...extra,
  });

  const handleSend = () => {
    const msg = inputValue.trim();
    if (!msg || isLoading) return;
    addMessage("user", msg);
    setOpen(true);
    setInputValue("");
    setLoading(true);
    mutation.mutate({
      message: msg,
      context: buildCtx(),
      history: history.slice(-10).map((m) => ({ role: m.role, content: m.content })),
    });
  };

  // Watch for programmatic commands from AIPanel (e.g. delete confirmation)
  useEffect(() => {
    if (!pendingCommand) return;
    setPendingCommand(null);
    addMessage("user", pendingCommand.displayText ?? "Confirmar");
    setOpen(true);
    setLoading(true);
    mutation.mutate({
      message: pendingCommand.message,
      context: buildCtx(pendingCommand.context),
      history: [],
    });
  }, [pendingCommand]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <header className="sticky top-0 z-30 h-16 bg-card/80 backdrop-blur border-b border-border flex items-center gap-3 px-4 md:px-6">
      <AIPanel />

      {/* Walix AI input — fills the flex-1 space */}
      <div
        data-tour="ai-prompt"
        className={cn(
          "flex-1 flex items-center gap-2 h-9 rounded-lg border px-3 transition-colors",
          "bg-muted/50 border-border/60",
          "focus-within:border-primary/40 focus-within:bg-background",
        )}
      >
        {/* ✦ toggle panel */}
        <button
          onClick={() => setOpen(!isOpen)}
          className="relative shrink-0 text-primary text-base leading-none hover:text-primary/80 transition-colors focus:outline-none"
          aria-label="Abrir panel Walix AI"
        >
          ✦
          {pendingSuggestionsCount > 0 && (
            <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-0.5 rounded-full
                             bg-accent text-[9px] font-bold text-accent-foreground
                             flex items-center justify-center leading-none">
              {pendingSuggestionsCount > 9 ? "9+" : pendingSuggestionsCount}
            </span>
          )}
        </button>

        <input
          ref={inputRef}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
          }}
          placeholder="Escribe una instrucción o pregunta…"
          disabled={isLoading}
          className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-50 min-w-0"
          aria-label="Walix AI"
        />

        <span className="hidden md:flex items-center gap-0.5 shrink-0 text-[10px] text-muted-foreground font-mono select-none">
          <kbd className="px-1 py-0.5 rounded border border-border text-[10px]">⌘</kbd>
          <kbd className="px-1 py-0.5 rounded border border-border text-[10px]">K</kbd>
        </span>

        <button
          onClick={handleSend}
          disabled={!inputValue.trim() || isLoading}
          className="shrink-0 p-1 rounded-md text-muted-foreground hover:text-primary disabled:opacity-30 transition-colors focus:outline-none"
          aria-label="Enviar"
        >
          {isLoading
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
            : <ArrowRight className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Copilot toggle button */}
      <button
        onClick={openCopilot}
        title="Abrir Copiloto (Ctrl+/)"
        className="shrink-0 p-2 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
        aria-label="Abrir Copiloto"
      >
        <Sparkles className="h-4 w-4" />
      </button>

      {/* User menu */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="rounded-full shrink-0">
            <Avatar className="h-9 w-9 border-2 border-primary/20">
              <AvatarFallback className="bg-gradient-brand text-primary-foreground text-xs font-semibold">
                {initials}
              </AvatarFallback>
            </Avatar>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel>
            <div className="font-medium">{user?.name ?? "Mi cuenta"}</div>
            <div className="text-xs text-muted-foreground font-normal truncate">{user?.email}</div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => navigate("/profile")}>
            <UserIcon className="h-4 w-4 mr-2" /> Perfil
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => window.dispatchEvent(new CustomEvent("walix:restart-tour"))}
          >
            <MapPin className="h-4 w-4 mr-2" /> Ver tour de bienvenida
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={signOut} className="text-danger focus:text-danger">
            <LogOut className="h-4 w-4 mr-2" /> Cerrar sesion
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
