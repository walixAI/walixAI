/**
 * C5 — CopilotDrawer: Sheet lateral del Copiloto conversacional.
 *
 * Atajo de teclado: Ctrl+/ (libre — J=CommandPalette, K=AIBar, B=Sidebar).
 * Sugerencias contextuales: array estático por ruta (sin llamadas backend extra).
 * Contexto de entidad: solo session_id="global" en esta versión; la inyección
 *   de entity_type/entity_id por página queda para un incremento posterior.
 */
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Loader2, MessageSquare, Plus, Send, Sparkles, X, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useCopilotStore } from "@/stores/copilot";

// ── Tool name display labels (matches COPILOT_TOOLS in backend) ───────────────

const TOOL_LABELS: Record<string, string> = {
  get_pipeline_status:   "Pipeline",
  search_contacts:       "Buscar contactos",
  get_contact_context:   "Contexto contacto",
  get_my_tasks:          "Mis tareas",
  get_my_suggestions:    "Sugerencias",
  get_my_deals:          "Mis deals",
  get_profitability:     "Rentabilidad",
  get_run_rate:          "Run rate",
  get_expenses_summary:  "Gastos",
  get_monthly_goal:      "Meta mensual",
  get_team_performance:  "Rendimiento equipo",
  create_contact:        "Crear contacto",
  create_deal:           "Crear deal",
  move_deal_stage:       "Mover deal",
  add_note:              "Agregar nota",
  create_task:           "Crear tarea",
  prepare_whatsapp_message: "Borrador WhatsApp",
  set_monthly_goal:      "Establecer meta",
};

// ── Route-based suggestion chips (static, no extra backend calls) ─────────────

const ROUTE_SUGGESTIONS: Record<string, string[]> = {
  "/dashboard":   ["¿Cuál es mi run rate este mes?", "¿Cuántos deals activos tengo?", "¿Qué tareas pendientes tengo hoy?"],
  "/pipeline":    ["¿Cuál es el valor total del pipeline?", "¿Qué deals llevan más tiempo sin avanzar?", "Muéstrame mis oportunidades activas"],
  "/contacts":    ["Busca un contacto por nombre", "¿Qué contactos necesitan seguimiento?"],
  "/tasks":       ["¿Cuáles son mis tareas más urgentes?", "Crea una tarea de seguimiento"],
  "/mi-dia":      ["¿Cuál es mi avance del mes?", "¿Tengo tareas vencidas?"],
  "/finance":     ["¿Cuál es mi rentabilidad este mes?", "¿Cómo van los gastos?"],
};

function getSuggestions(pathname: string): string[] {
  for (const [prefix, suggs] of Object.entries(ROUTE_SUGGESTIONS)) {
    if (pathname.startsWith(prefix)) return suggs;
  }
  return ["¿En qué puedo ayudarte hoy?", "¿Cuál es mi rendimiento este mes?", "¿Cuántos deals activos tengo?"];
}

// ── Markdown renderer (self-contained, no external deps) ──────────────────────

function renderMarkdown(text: string): string {
  // Split out code blocks first to protect them from inline processing
  const parts: { type: "text" | "code"; content: string; lang?: string }[] = [];
  const codeBlockRe = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIdx = 0;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRe.exec(text)) !== null) {
    if (match.index > lastIdx) {
      parts.push({ type: "text", content: text.slice(lastIdx, match.index) });
    }
    parts.push({ type: "code", lang: match[1] || undefined, content: match[2].trimEnd() });
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < text.length) {
    parts.push({ type: "text", content: text.slice(lastIdx) });
  }

  const processText = (raw: string): string => {
    const lines = raw.split("\n");
    const out: string[] = [];
    let inList = false;
    let inTable = false;
    let tableHeaderDone = false;

    const flushList = () => { if (inList) { out.push("</ul>"); inList = false; } };
    const flushTable = () => { if (inTable) { out.push("</tbody></table>"); inTable = false; tableHeaderDone = false; } };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // Table rows
      if (/^\s*\|/.test(line)) {
        flushList();
        if (!inTable) {
          out.push('<table class="copilot-table">');
          inTable = true;
        }
        // Separator row (e.g. |---|---|)
        if (/^\s*\|[\s\-:|]+\|/.test(line) && !/[a-zA-Z]/.test(line)) {
          if (!tableHeaderDone) {
            out.push("</thead><tbody>");
            tableHeaderDone = true;
          }
          continue;
        }
        const cells = line.split("|").slice(1, -1).map((c) => c.trim());
        const tag = !tableHeaderDone ? "th" : "td";
        if (!tableHeaderDone) out.push("<thead><tr>");
        else out.push("<tr>");
        cells.forEach((c) => out.push(`<${tag}>${inlineFormat(c)}</${tag}>`));
        out.push("</tr>");
        if (!tableHeaderDone && !lines[i + 1]?.match(/^\s*\|[\s\-:|]+\|/)) {
          out.push("</thead><tbody>");
          tableHeaderDone = true;
        }
        continue;
      }
      flushTable();

      // Unordered list items
      if (/^[-*]\s/.test(line)) {
        if (!inList) { out.push('<ul class="copilot-list">'); inList = true; }
        out.push(`<li>${inlineFormat(line.slice(2))}</li>`);
        continue;
      }
      flushList();

      // Headings
      const hMatch = line.match(/^(#{1,3})\s+(.+)/);
      if (hMatch) {
        const level = Math.min(hMatch[1].length, 3);
        out.push(`<h${level} class="copilot-h${level}">${inlineFormat(hMatch[2])}</h${level}>`);
        continue;
      }

      // Blank line
      if (line.trim() === "") {
        out.push("<br/>");
        continue;
      }

      // Normal paragraph
      out.push(`<p>${inlineFormat(line)}</p>`);
    }

    flushList();
    flushTable();
    return out.join("");
  };

  const inlineFormat = (s: string): string =>
    s
      // Bold
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      // Italic (single *, not **)
      .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>")
      // Inline code
      .replace(/`([^`]+)`/g, '<code class="copilot-code">$1</code>');

  return parts
    .map((p) =>
      p.type === "code"
        ? `<pre class="copilot-pre"><code>${escapeHtml(p.content)}</code></pre>`
        : processText(p.content),
    )
    .join("");
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({
  role,
  content,
  toolsUsed,
  isError,
}: {
  role: "user" | "assistant";
  content: string;
  toolsUsed: string[];
  isError: boolean;
}) {
  const isUser = role === "user";

  return (
    <div className={cn("flex flex-col gap-1", isUser ? "items-end" : "items-start")}>
      {/* Bubble */}
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : isError
              ? "bg-danger/10 text-danger border border-danger/20 rounded-bl-sm"
              : "bg-muted text-foreground rounded-bl-sm",
        )}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{content}</span>
        ) : (
          <div
            className="copilot-md"
            // renderMarkdown produces controlled HTML from Claude — safe subst set.
            dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
          />
        )}
      </div>

      {/* Tool badges */}
      {toolsUsed.length > 0 && (
        <div className="flex flex-wrap gap-1 px-1">
          {toolsUsed.map((tool) => (
            <Badge
              key={tool}
              variant="secondary"
              className="text-[10px] h-5 gap-1 font-normal text-muted-foreground"
            >
              <Wrench className="h-2.5 w-2.5" />
              {TOOL_LABELS[tool] ?? tool}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Thinking indicator ─────────────────────────────────────────────────────────

function ThinkingBubble() {
  return (
    <div className="flex items-start gap-2">
      <div className="bg-muted rounded-2xl rounded-bl-sm px-4 py-2.5 flex items-center gap-2">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Pensando…</span>
      </div>
    </div>
  );
}

// ── Main drawer ───────────────────────────────────────────────────────────────

export function CopilotDrawer() {
  const {
    open,
    messages,
    status,
    closeDrawer,
    send,
    newConversation,
  } = useCopilotStore();

  const { pathname } = useLocation();
  const suggestions = getSuggestions(pathname);

  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, status]);

  // Ctrl+/ shortcut — Ctrl+J taken by CommandPalette, Ctrl+K by AIBar, Ctrl+B by Sidebar
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "/") {
        e.preventDefault();
        useCopilotStore.getState().open
          ? useCopilotStore.getState().closeDrawer()
          : useCopilotStore.getState().openDrawer();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const handleSend = () => {
    const text = input.trim();
    if (!text || status !== "idle") return;
    setInput("");
    send(text);
  };

  const handleSuggestion = (text: string) => {
    setInput(text);
    textareaRef.current?.focus();
  };

  const isEmpty = messages.length === 0 && status === "idle";

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) closeDrawer(); }}>
      <SheetContent
        side="right"
        className="w-full sm:w-[420px] sm:max-w-[420px] p-0 flex flex-col"
      >
        {/* Header */}
        <SheetHeader className="px-4 py-3 border-b border-border flex-none">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              <SheetTitle className="text-sm font-semibold">Walix Copiloto</SheetTitle>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={newConversation}
                title="Nueva conversación"
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              >
                <Plus className="h-4 w-4" />
              </button>
              <button
                onClick={closeDrawer}
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        </SheetHeader>

        {/* Messages */}
        <ScrollArea className="flex-1 min-h-0">
          <div ref={scrollRef} className="px-4 py-4 space-y-4">
            {isEmpty ? (
              /* Empty state */
              <div className="flex flex-col items-center justify-center py-12 gap-4 text-center">
                <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                  <MessageSquare className="h-6 w-6 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">Hola, soy tu Copiloto</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Pregúntame sobre tu pipeline, clientes, metas o cualquier dato de tu negocio.
                  </p>
                </div>

                {/* Suggestion chips */}
                <div className="flex flex-wrap gap-2 justify-center">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => handleSuggestion(s)}
                      className="text-xs px-3 py-1.5 rounded-full border border-border bg-muted/50
                                 hover:bg-muted text-muted-foreground hover:text-foreground
                                 transition-colors text-left"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((msg) => (
                  <MessageBubble
                    key={msg.id}
                    role={msg.role}
                    content={msg.content}
                    toolsUsed={msg.toolsUsed}
                    isError={msg.isError}
                  />
                ))}
                {status === "thinking" || status === "executing" ? (
                  <ThinkingBubble />
                ) : null}
              </>
            )}
          </div>
        </ScrollArea>

        {/* Input area */}
        <div className="flex-none border-t border-border px-4 py-3 bg-card">
          {/* Suggestion chips (when conversation is non-empty, show a collapsed row) */}
          {!isEmpty && (
            <div className="flex gap-1.5 mb-2 overflow-x-auto pb-1 scrollbar-none">
              {suggestions.slice(0, 2).map((s) => (
                <button
                  key={s}
                  onClick={() => handleSuggestion(s)}
                  className="shrink-0 text-[11px] px-2.5 py-1 rounded-full border border-border
                             bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground
                             transition-colors whitespace-nowrap"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          <div className="flex items-end gap-2">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Escribe un mensaje… (Enter para enviar)"
              disabled={status !== "idle"}
              rows={1}
              className="flex-1 resize-none min-h-[38px] max-h-[120px] text-sm py-2"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || status !== "idle"}
              className={cn(
                "shrink-0 h-[38px] w-[38px] rounded-lg flex items-center justify-center transition-colors",
                "bg-primary text-primary-foreground",
                "hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed",
              )}
              aria-label="Enviar"
            >
              {status !== "idle" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </button>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1.5 text-center">
            <kbd className="font-mono">Ctrl+/</kbd> para abrir/cerrar · Enter para enviar · Shift+Enter para nueva línea
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
