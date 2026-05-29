"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  api,
  getToken,
  type ConversationOut,
  type LeadDetail,
  type MessageOut,
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
  const hasQualification = Object.keys(qd).length > 0;

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

          <section className="bg-white border border-slate-200 rounded-lg p-4">
            <h2 className="font-medium mb-3">Calificación</h2>
            {!hasQualification ? (
              <p className="text-sm text-slate-500">Sin datos aún.</p>
            ) : (
              <dl className="space-y-2 text-sm">
                {qd.parent_name && (
                  <div>
                    <dt className="text-slate-500">Padre/Madre</dt>
                    <dd>{String(qd.parent_name)}</dd>
                  </div>
                )}
                {qd.child_age != null && (
                  <div>
                    <dt className="text-slate-500">Edad del niño</dt>
                    <dd>{String(qd.child_age)} años</dd>
                  </div>
                )}
                {qd.consultation_reason && (
                  <div>
                    <dt className="text-slate-500">Motivo</dt>
                    <dd>{String(qd.consultation_reason)}</dd>
                  </div>
                )}
                {qd.parent_city && (
                  <div>
                    <dt className="text-slate-500">Ciudad</dt>
                    <dd>{String(qd.parent_city)}</dd>
                  </div>
                )}
                {qd.branch_suggested && (
                  <div>
                    <dt className="text-slate-500">Sucursal sugerida</dt>
                    <dd>{String(qd.branch_suggested)}</dd>
                  </div>
                )}
                {lead.qualification_score != null && (
                  <div>
                    <dt className="text-slate-500">Score</dt>
                    <dd>{(Number(lead.qualification_score) * 100).toFixed(0)}%</dd>
                  </div>
                )}
              </dl>
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
          <div className="px-4 py-3 border-b border-slate-200 font-medium">
            Conversación
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 ? (
              <p className="text-sm text-slate-500 text-center">
                Sin mensajes todavía.
              </p>
            ) : (
              messages.map((m) => <MessageBubble key={m.id} message={m} />)
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
