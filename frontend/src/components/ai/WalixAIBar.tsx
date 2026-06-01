import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Minus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useAIBarStore, type AIBarAction } from "@/stores/aiBarStore";
import { ScrollArea } from "@/components/ui/scroll-area";

// ── Suggested action chip ─────────────────────────────────────────────────────

function ActionChip({ action }: { action: AIBarAction }) {
  return (
    <button
      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs
                 bg-primary/20 text-primary-foreground border border-primary/30
                 hover:bg-primary/30 transition-colors"
      onClick={() => {
        // Future: dispatch action to the relevant store/page
        console.info("AI action dispatched:", action);
      }}
    >
      {action.label}
    </button>
  );
}

// ── Conversation panel (right side) ──────────────────────────────────────────

function AIPanel() {
  const { history, isLoading, setOpen, clear } = useAIBarStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, isLoading]);

  return (
    <div className="dark fixed right-0 top-0 bottom-0 z-40 w-full max-w-sm xl:max-w-md
                    flex flex-col bg-card border-l border-border shadow-2xl
                    animate-in slide-in-from-right duration-300">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-primary text-base leading-none">✦</span>
          <span className="text-sm font-semibold text-foreground">Walix AI</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={clear}
            className="text-muted-foreground hover:text-foreground text-xs px-2 py-1 rounded transition-colors"
          >
            Limpiar
          </button>
          <button
            onClick={() => setOpen(false)}
            className="text-muted-foreground hover:text-foreground p-1 rounded transition-colors"
            aria-label="Cerrar panel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 px-4 py-3">
        {history.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center h-40 gap-2 text-center">
            <span className="text-primary text-3xl">✦</span>
            <p className="text-sm text-muted-foreground">
              Escribe una instrucción o pregunta.<br />
              Walix actúa directamente en tu CRM.
            </p>
          </div>
        )}

        <div className="space-y-4">
          {history.map((msg, i) => (
            <div
              key={i}
              className={cn(
                "flex flex-col gap-1.5",
                msg.role === "user" ? "items-end" : "items-start",
              )}
            >
              <div
                className={cn(
                  "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground rounded-br-sm"
                    : "bg-muted text-foreground rounded-bl-sm",
                )}
              >
                {msg.content}
              </div>

              {/* Suggested actions */}
              {msg.suggested_actions && msg.suggested_actions.length > 0 && (
                <div className="flex flex-wrap gap-1.5 max-w-[85%]">
                  {msg.suggested_actions.map((a, j) => (
                    <ActionChip key={j} action={a} />
                  ))}
                </div>
              )}
            </div>
          ))}

          {/* Thinking indicator */}
          {isLoading && (
            <div className="flex items-start gap-2">
              <div className="bg-muted rounded-2xl rounded-bl-sm px-3.5 py-2 text-sm text-muted-foreground
                              flex items-center gap-2">
                <span className="text-primary animate-pulse">✦</span>
                Walix está pensando…
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </ScrollArea>
    </div>
  );
}

// ── Main bar ──────────────────────────────────────────────────────────────────

export function WalixAIBar() {
  const {
    isOpen, isMinimized,
    history, currentContext, isLoading,
    setOpen, setMinimized, addMessage, setLoading,
  } = useAIBarStore();

  const [inputValue, setInputValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // ⌘K / Ctrl+K shortcut
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (isMinimized) setMinimized(false);
        setTimeout(() => inputRef.current?.focus(), 50);
      }
      if (e.key === "Escape") {
        inputRef.current?.blur();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isMinimized, setMinimized]);

  const mutation = useMutation({
    mutationFn: api.sendAICommand,
    onSuccess: (data) => {
      addMessage("assistant", data.reply, data.suggested_actions);
      setLoading(false);
    },
    onError: () => {
      addMessage("assistant", "Ocurrió un error al procesar tu instrucción. Intenta de nuevo.");
      setLoading(false);
    },
  });

  const handleSend = () => {
    const msg = inputValue.trim();
    if (!msg || isLoading) return;

    addMessage("user", msg);
    setOpen(true);
    setInputValue("");
    setLoading(true);

    // Last 5 turns for context
    const recentHistory = history
      .slice(-10)
      .map((m) => ({ role: m.role, content: m.content }));

    mutation.mutate({
      message: msg,
      context: currentContext,
      history: recentHistory,
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Minimized strip ────────────────────────────────────────────────────────
  if (isMinimized) {
    return (
      <div className="fixed bottom-16 md:bottom-0 inset-x-0 z-50 group">
        {/* Gradient strip */}
        <div
          className="h-1 w-full"
          style={{
            background:
              "linear-gradient(to right, hsl(244,75%,25%), hsl(239,84%,60%), hsl(189,94%,43%))",
          }}
        />
        {/* Restore chip on hover */}
        <div
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2
                     opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none group-hover:pointer-events-auto"
        >
          <button
            onClick={() => setMinimized(false)}
            className="flex items-center gap-1.5 bg-primary text-primary-foreground
                       px-3 py-1.5 rounded-full text-xs font-medium shadow-lg
                       hover:bg-primary/90 transition-colors"
          >
            <span className="text-sm leading-none">✦</span>
            Walix AI
          </button>
        </div>
      </div>
    );
  }

  // ── Full bar + panel ───────────────────────────────────────────────────────
  return (
    <>
      {/* Side panel */}
      {isOpen && <AIPanel />}

      {/* Bottom bar */}
      <div
        className="dark fixed bottom-16 md:bottom-0 inset-x-0 z-50
                   bg-[hsl(222,47%,7%)] border-t border-[hsl(217,33%,17%)]"
      >
        <div className="flex items-center gap-2 px-3 md:px-4 h-14 max-w-screen-2xl mx-auto">
          {/* ✦ icon */}
          <button
            onClick={() => setOpen(!isOpen)}
            className="shrink-0 text-primary text-lg leading-none hover:text-primary/80
                       transition-colors focus:outline-none"
            aria-label="Abrir panel Walix AI"
            title="Walix AI"
          >
            ✦
          </button>

          {/* Input */}
          <input
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Escribe una instrucción o pregunta…"
            disabled={isLoading}
            className="flex-1 bg-transparent text-sm text-white placeholder:text-[hsl(215,16%,47%)]
                       focus:outline-none disabled:opacity-50"
            aria-label="Walix AI input"
          />

          {/* ⌘K hint */}
          <span className="hidden md:flex items-center gap-0.5 shrink-0 text-xs
                           text-[hsl(215,16%,47%)] font-mono select-none">
            <kbd className="px-1 py-0.5 rounded border border-[hsl(217,33%,25%)] text-[10px]">⌘</kbd>
            <kbd className="px-1 py-0.5 rounded border border-[hsl(217,33%,25%)] text-[10px]">K</kbd>
          </span>

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading}
            className="shrink-0 p-1.5 rounded-lg bg-primary text-primary-foreground
                       hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors"
            aria-label="Enviar"
          >
            <ArrowRight className="h-4 w-4" />
          </button>

          {/* Minimize button */}
          <button
            onClick={() => setMinimized(true)}
            className="shrink-0 p-1.5 rounded-lg text-[hsl(215,16%,47%)]
                       hover:text-white hover:bg-[hsl(217,33%,17%)] transition-colors"
            aria-label="Minimizar Walix AI"
          >
            <Minus className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  );
}
