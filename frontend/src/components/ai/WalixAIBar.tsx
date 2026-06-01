import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Minus } from "lucide-react";
import { api } from "@/lib/api";
import { useAIBarStore } from "@/stores/aiBarStore";
import { AIPanel } from "./AIPanel";

export function WalixAIBar() {
  const {
    isOpen, isMinimized,
    history, currentContext, isLoading, draftInput,
    setOpen, setMinimized, addMessage, setLoading, setDraftInput,
  } = useAIBarStore();

  const [inputValue, setInputValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Consume draft text pushed by suggested-action chips
  useEffect(() => {
    if (draftInput) {
      setInputValue(draftInput);
      setDraftInput("");
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [draftInput, setDraftInput]);

  // ⌘K / Ctrl+K focuses the input; Escape blurs it
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (isMinimized) setMinimized(false);
        setTimeout(() => inputRef.current?.focus(), 50);
      }
      if (e.key === "Escape") inputRef.current?.blur();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isMinimized, setMinimized]);

  const mutation = useMutation({
    mutationFn: api.sendAICommand,
    onSuccess: (data) => {
      addMessage("assistant", data.response_text, data.suggested_actions);
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

    mutation.mutate({
      message: msg,
      context: currentContext,
      history: history.slice(-10).map((m) => ({ role: m.role, content: m.content })),
    });
  };

  // ── Minimized strip ──────────────────────────────────────────────────────
  if (isMinimized) {
    return (
      <div className="fixed bottom-16 md:bottom-0 inset-x-0 z-50 group">
        <div
          className="h-1 w-full"
          style={{
            background:
              "linear-gradient(to right, hsl(244,75%,25%), hsl(239,84%,60%), hsl(189,94%,43%))",
          }}
        />
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2
                        opacity-0 group-hover:opacity-100 transition-opacity duration-150
                        pointer-events-none group-hover:pointer-events-auto">
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

  // ── Full bar + panel ─────────────────────────────────────────────────────
  return (
    <>
      {/* The Sheet panel is always mounted; Sheet.open controls visibility */}
      <AIPanel />

      <div className="dark fixed bottom-16 md:bottom-0 inset-x-0 z-50
                      bg-[hsl(222,47%,7%)] border-t border-[hsl(217,33%,17%)]">
        <div className="flex items-center gap-2 px-3 md:px-4 h-14 max-w-screen-2xl mx-auto">
          {/* ✦ toggle panel */}
          <button
            onClick={() => setOpen(!isOpen)}
            className="shrink-0 text-primary text-lg leading-none hover:text-primary/80
                       transition-colors focus:outline-none"
            aria-label="Abrir panel Walix AI"
          >
            ✦
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
            className="flex-1 bg-transparent text-sm text-white
                       placeholder:text-[hsl(215,16%,47%)]
                       focus:outline-none disabled:opacity-50"
            aria-label="Walix AI"
          />

          <span className="hidden md:flex items-center gap-0.5 shrink-0 text-xs
                           text-[hsl(215,16%,47%)] font-mono select-none">
            <kbd className="px-1 py-0.5 rounded border border-[hsl(217,33%,25%)] text-[10px]">⌘</kbd>
            <kbd className="px-1 py-0.5 rounded border border-[hsl(217,33%,25%)] text-[10px]">K</kbd>
          </span>

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

          <button
            onClick={() => setMinimized(true)}
            className="shrink-0 p-1.5 rounded-lg text-[hsl(215,16%,47%)]
                       hover:text-white hover:bg-[hsl(217,33%,17%)] transition-colors"
            aria-label="Minimizar"
          >
            <Minus className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  );
}
