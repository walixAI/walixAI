import { useRef, useState } from "react";
import { Send, Loader2, CheckCircle2, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { toast } from "sonner";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  useBuilderChat,
  useSaveCapability,
  type BuilderMessage,
  type BuilderSaveRequest,
} from "@/lib/queries/walixBuilder";

interface Props {
  open: boolean;
  onClose: () => void;
}

function extractRecipe(text: string): BuilderSaveRequest | null {
  if (!text.includes("RECIPE_READY")) return null;
  const match = text.match(/```json\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    return JSON.parse(match[1]) as BuilderSaveRequest;
  } catch {
    return null;
  }
}

export function NewCapabilityWizard({ open, onClose }: Props) {
  const [messages, setMessages] = useState<BuilderMessage[]>([]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const chatMutation = useBuilderChat();
  const saveMutation = useSaveCapability();

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const pendingRecipe = lastAssistant ? extractRecipe(lastAssistant.content) : null;

  async function sendMessage() {
    const text = input.trim();
    if (!text || chatMutation.isPending) return;
    setInput("");

    const nextMessages: BuilderMessage[] = [...messages, { role: "user", content: text }];
    setMessages(nextMessages);

    try {
      const { reply } = await chatMutation.mutateAsync(nextMessages);
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch {
      toast.error("Error al conectar con el asistente");
      setMessages((prev) => prev.slice(0, -1));
      setInput(text);
    }
  }

  async function handleSave() {
    if (!pendingRecipe) return;
    try {
      await saveMutation.mutateAsync(pendingRecipe);
      toast.success("Capacidad guardada correctamente");
      handleClose();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error al guardar";
      toast.error(msg);
    }
  }

  function handleClose() {
    setMessages([]);
    setInput("");
    onClose();
  }

  return (
    <Sheet open={open} onOpenChange={(v) => !v && handleClose()}>
      <SheetContent side="right" className="w-full sm:max-w-lg flex flex-col p-0">
        <SheetHeader className="px-5 pt-5 pb-3 border-b border-border shrink-0">
          <div className="flex items-center justify-between">
            <SheetTitle className="text-base">Nueva capacidad</SheetTitle>
            <button onClick={handleClose} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            Describe qué quieres automatizar y el asistente diseñará la receta.
          </p>
        </SheetHeader>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.length === 0 && (
            <div className="text-center py-10 text-sm text-muted-foreground">
              <p className="font-medium">¿Qué quieres automatizar?</p>
              <p className="text-xs mt-1">
                Ejemplo: "Cuando un asesor diga 'nuevo lead rápido', crear un contacto y una tarea de seguimiento"
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={
                m.role === "user"
                  ? "flex justify-end"
                  : "flex justify-start"
              }
            >
              <div
                className={
                  m.role === "user"
                    ? "bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-3 py-2 text-sm max-w-[85%]"
                    : "bg-muted rounded-2xl rounded-tl-sm px-3 py-2 text-sm max-w-[90%] prose prose-sm dark:prose-invert"
                }
              >
                {m.role === "assistant" ? (
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                ) : (
                  m.content
                )}
              </div>
            </div>
          ))}
          {chatMutation.isPending && (
            <div className="flex justify-start">
              <div className="bg-muted rounded-2xl rounded-tl-sm px-3 py-2">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Save recipe banner */}
        {pendingRecipe && (
          <div className="mx-4 mb-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 flex items-center justify-between gap-3 shrink-0">
            <div className="flex items-center gap-2 text-emerald-700 text-sm font-medium">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              Receta lista: <span className="font-semibold">{pendingRecipe.name}</span>
            </div>
            <Button
              size="sm"
              className="shrink-0 bg-emerald-600 hover:bg-emerald-700"
              onClick={handleSave}
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                "Guardar"
              )}
            </Button>
          </div>
        )}

        {/* Input */}
        <div className="px-4 pb-4 shrink-0 border-t border-border pt-3 flex gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
            placeholder="Describe la automatización…"
            rows={2}
            className="resize-none text-sm flex-1"
          />
          <Button
            size="icon"
            onClick={sendMessage}
            disabled={!input.trim() || chatMutation.isPending}
            className="shrink-0 self-end"
          >
            {chatMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
