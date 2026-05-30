"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  api,
  getToken,
  type ConversationOut,
  type LeadDetail,
  type MessageOut,
  type UserBrief,
} from "@/lib/api";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("es-MX", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("es-MX", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function MessageBubble({ message }: { message: MessageOut }) {
  const isLead = message.role === "user";
  return (
    <div className={`flex ${isLead ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
          isLead
            ? "bg-blue-100 text-blue-900"
            : "bg-slate-100 text-slate-900"
        }`}
      >
        <div>{message.content}</div>
        <div className="text-xs opacity-60 mt-1">
          {formatTime(message.created_at)}
        </div>
      </div>
    </div>
  );
}

export default function LeadDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [conversation, setConversation] = useState<ConversationOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [assignees, setAssignees] = useState<UserBrief[] | null>(null);
  const [selectedAssignee, setSelectedAssignee] = useState("");
  const [assigning, setAssigning] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const [l, c] = await Promise.all([
        api.getLead(id),
        api.getConversation(id),
      ]);
      setLead(l);
      setConversation(c);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error cargando lead");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    load();
    const interval = setInterval(load, 5_000);
    return () => clearInterval(interval);
  }, [router, load]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation?.messages]);

  async function sendMessage() {
    if (!draft.trim() || sending) return;
    setSending(true);
    setError(null);
    try {
      await api.sendMessage(id, draft.trim());
      setDraft("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al enviar mensaje");
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  async function openAssign() {
    if (assignees !== null) { setAssignees(null); return; }
    try {
      const list = await api.listAssignees(id);
      setAssignees(list);
      setSelectedAssignee(list[0]?.id ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error cargando usuarios");
    }
  }

  async function confirmAssign() {
    if (!selectedAssignee || assigning) return;
    setAssigning(true);
    setError(null);
    try {
      await api.assignLead(id, selectedAssignee);
      setAssignees(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al asignar");
    } finally {
      setAssigning(false);
    }
  }

  async function takeOver() {
    setBusy(true);
    setError(null);
    try {
      await api.handoff(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al tomar control");
    } finally {
      setBusy(false);
    }
  }

  async function returnToBot() {
    setBusy(true);
    setError(null);
    try {
      await api.returnToBot(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al devolver al bot");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-slate-500">
        Cargando…
      </div>
    );
  }
  if (error && !lead) {
    return (
      <div className="min-h-screen p-6">
        <Link href="/dashboard" className="text-sm text-slate-600 hover:text-slate-900">
          ← Volver al dashboard
        </Link>
        <p className="mt-4 text-sm text-red-600">{error}</p>
      </div>
    );
  }
  if (!lead) return null;

  const canTakeOver = conversation?.handled_by === "bot";
  const isHuman = conversation?.handled_by === "human";
  const messages = conversation?.messages ?? [];
  const qd = lead.qualification_data ?? {};
  const score = lead.qualification_score ?? 0;
  const scorePct = Math.round(score * 100);
  const scoreBarColor =
    score >= 0.8 ? "bg-emerald-500" : score >= 0.5 ? "bg-amber-400" : "bg-red-400";

  const qStatus = String(qd.qualification_status ?? "");
  const qStatusBadge: Record<string, { label: string; cls: string }> = {
    calificado:    { label: "Calificado ✓",  cls: "bg-emerald-100 text-emerald-700 ring-emerald-200" },
    incompleto:    { label: "En proceso...",  cls: "bg-amber-100 text-amber-700 ring-amber-200" },
    no_calificado: { label: "No califica",    cls: "bg-slate-100 text-slate-600 ring-slate-200" },
    escalar:       { label: "Escalado",       cls: "bg-red-100 text-red-700 ring-red-200" },
  };
  const badge = qStatusBadge[qStatus] ?? { label: "Sin evaluar", cls: "bg-slate-100 text-slate-500 ring-slate-200" };

  const QUAL_FIELDS: { key: string; label: string }[] = [
    { key: "parent_name",        label: "Nombre del padre" },
    { key: "child_age",          label: "Edad del niño" },
    { key: "consultation_reason",label: "Motivo" },
    { key: "parent_city",        label: "Ciudad" },
  ];
  const missingFields = QUAL_FIELDS.filter(
    (f) => qd[f.key] == null || qd[f.key] === ""
  ).map((f) => f.label.toLowerCase());

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link
            href="/dashboard"
            className="text-sm text-slate-600 hover:text-slate-900"
          >
            ← Volver
          </Link>
          <h1 className="font-semibold truncate max-w-[60%] text-center">
            {lead.name ?? lead.wa_phone}
          </h1>
          <div className="w-16" />
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
        <aside className="lg:col-span-1 space-y-4">
          <section className="bg-white border border-slate-200 rounded-lg p-4">
            <h2 className="font-medium mb-3">Datos del lead</h2>
            <dl className="space-y-2 text-sm">
              <div>
                <dt className="text-slate-500">Nombre</dt>
                <dd>{lead.name ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Teléfono WhatsApp</dt>
                <dd>{lead.wa_phone}</dd>
              </div>
              {lead.contact_phone && (
                <div>
                  <dt className="text-slate-500">Teléfono de contacto</dt>
                  <dd>{lead.contact_phone}</dd>
                </div>
              )}
              <div>
                <dt className="text-slate-500">Status</dt>
                <dd>{lead.status}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Sentimiento</dt>
                <dd>{lead.sentiment}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Asignado a</dt>
                <dd>{lead.assigned_to_name ?? "Sin asignar"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Manejado por</dt>
                <dd>{conversation?.handled_by ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Origen</dt>
                <dd>{lead.source}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Creado</dt>
                <dd>{formatDateTime(lead.created_at)}</dd>
              </div>
            </dl>
          </section>

          <section className="bg-white border border-slate-200 rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-medium">Calificación</h2>
              <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ring-1 ${badge.cls}`}>
                {badge.label}
              </span>
            </div>

            {/* Progress bar */}
            <div>
              <div className="flex justify-between text-xs text-slate-500 mb-1">
                <span>Progreso</span>
                <span>{scorePct}%</span>
              </div>
              <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${scoreBarColor}`}
                  style={{ width: `${scorePct}%` }}
                />
              </div>
            </div>

            {/* Data fields */}
            <dl className="space-y-1.5 text-sm">
              {QUAL_FIELDS.map((f) => {
                const val = qd[f.key];
                const display =
                  f.key === "child_age" && val != null
                    ? `${val} años`
                    : val != null && val !== ""
                    ? String(val)
                    : null;
                return (
                  <div key={f.key} className="flex justify-between gap-2">
                    <dt className="text-slate-500 shrink-0">{f.label}</dt>
                    <dd className={display ? "text-right" : "text-slate-300 text-right"}>
                      {display ?? "pendiente"}
                    </dd>
                  </div>
                );
              })}
              {typeof qd.branch_suggested === "string" && qd.branch_suggested && (
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500 shrink-0">Sucursal</dt>
                  <dd className="text-right">{qd.branch_suggested}</dd>
                </div>
              )}
            </dl>

            {/* Missing fields hint */}
            {missingFields.length > 0 && (
              <p className="text-xs text-slate-400">
                Falta: {missingFields.join(", ")}
              </p>
            )}
          </section>

          {canTakeOver && (
            <button
              onClick={takeOver}
              disabled={busy}
              className="w-full bg-amber-500 text-white py-2 rounded-md font-medium hover:bg-amber-600 disabled:opacity-50 transition"
            >
              {busy ? "Tomando control…" : "Tomar control de la conversación"}
            </button>
          )}
          {isHuman && (
            <div className="space-y-2">
              <div className="bg-amber-50 border border-amber-200 text-amber-800 text-sm p-3 rounded-md">
                Estás manejando esta conversación manualmente. El bot no
                responderá hasta que lo reactives.
              </div>

              {/* Assign to doctor */}
              <button
                onClick={openAssign}
                className="w-full bg-indigo-600 text-white py-2 rounded-md font-medium hover:bg-indigo-700 transition"
              >
                {assignees !== null ? "Cancelar asignación" : "Asignar al médico"}
              </button>
              {assignees !== null && (
                <div className="space-y-2">
                  <select
                    value={selectedAssignee}
                    onChange={(e) => setSelectedAssignee(e.target.value)}
                    className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  >
                    {assignees.length === 0 && (
                      <option value="">Sin usuarios disponibles</option>
                    )}
                    {assignees.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name} ({u.role})
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={confirmAssign}
                    disabled={assigning || !selectedAssignee}
                    className="w-full bg-indigo-500 text-white py-2 rounded-md font-medium hover:bg-indigo-600 disabled:opacity-50 transition"
                  >
                    {assigning ? "Asignando…" : "Confirmar asignación"}
                  </button>
                </div>
              )}

              <button
                onClick={returnToBot}
                disabled={busy}
                className="w-full bg-slate-700 text-white py-2 rounded-md font-medium hover:bg-slate-800 disabled:opacity-50 transition"
              >
                {busy ? "Reactivando…" : "Devolver al bot"}
              </button>
            </div>
          )}

          {error && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {error}
            </div>
          )}
        </aside>

        <section className="lg:col-span-2 bg-white border border-slate-200 rounded-lg flex flex-col h-[70vh]">
          <div className="px-4 py-3 border-b border-slate-200 font-medium flex items-center justify-between">
            <span>Conversación</span>
            {isHuman && (
              <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                Control manual
              </span>
            )}
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 ? (
              <p className="text-sm text-slate-500 text-center">
                Sin mensajes todavía.
              </p>
            ) : (
              messages.map((m) => <MessageBubble key={m.id} message={m} />)
            )}
            <div ref={messagesEndRef} />
          </div>

          {isHuman && (
            <div className="border-t border-slate-200 p-3 flex gap-2 items-end">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Escribe un mensaje… (Enter para enviar, Shift+Enter para nueva línea)"
                rows={2}
                disabled={sending}
                className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:opacity-50"
              />
              <button
                onClick={sendMessage}
                disabled={sending || !draft.trim()}
                className="shrink-0 bg-amber-500 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-amber-600 disabled:opacity-40 transition"
              >
                {sending ? "…" : "Enviar"}
              </button>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
