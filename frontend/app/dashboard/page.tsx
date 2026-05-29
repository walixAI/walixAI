"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  api,
  clearToken,
  getToken,
  type LeadListItem,
  type LeadSentiment,
  type LeadStatus,
  type UserMe,
} from "@/lib/api";

const POLL_INTERVAL_MS = 15_000;

const STATUS_FILTERS: { value: LeadStatus | "all"; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "nuevo", label: "Nuevos" },
  { value: "en_calificacion", label: "En calificación" },
  { value: "calificado", label: "Calificados" },
  { value: "escalado", label: "Escalados" },
  { value: "perdido", label: "Perdidos" },
];

const STATUS_META: Record<LeadStatus, { label: string; cls: string }> = {
  nuevo:           { label: "Nuevo",           cls: "bg-blue-100 text-blue-700 ring-blue-200" },
  en_calificacion: { label: "En calificación", cls: "bg-amber-100 text-amber-700 ring-amber-200" },
  calificado:      { label: "Calificado",      cls: "bg-emerald-100 text-emerald-700 ring-emerald-200" },
  escalado:        { label: "Escalado",        cls: "bg-red-100 text-red-700 ring-red-200" },
  perdido:         { label: "Perdido",         cls: "bg-slate-100 text-slate-600 ring-slate-200" },
};

function sentimentLabel(s: LeadSentiment): string {
  switch (s) {
    case "neutral":
      return "Neutral";
    case "interesado":
      return "Interesado";
    case "urgente":
      return "Urgente";
    case "negativo":
      return "Negativo";
  }
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("es-MX", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

const MX_TZ = "America/Mexico_City";

function todayStr(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: MX_TZ });
}

function yesterdayStr(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toLocaleDateString("en-CA", { timeZone: MX_TZ });
}

function formatDateLabel(dateStr: string): string {
  if (dateStr === todayStr()) return "Hoy";
  if (dateStr === yesterdayStr()) return "Ayer";
  return new Date(dateStr + "T12:00:00").toLocaleDateString("es-MX", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserMe | null>(null);
  const [leads, setLeads] = useState<LeadListItem[]>([]);
  const [filter, setFilter] = useState<LeadStatus | "all">("all");
  const [date, setDate] = useState<string>(todayStr());
  const [allDates, setAllDates] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => router.replace("/login"));
  }, [router]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const opts: Parameters<typeof api.listLeads>[0] = allDates ? { all: true } : { date };
        if (filter !== "all") opts.status = filter;
        const res = await api.listLeads(opts);
        if (cancelled) return;
        setLeads(res.items);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error cargando leads");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [filter, date, allDates]);

  function prevDay() {
    const d = new Date(date + "T12:00:00");
    d.setDate(d.getDate() - 1);
    setDate(d.toISOString().slice(0, 10));
    setLoading(true);
  }

  function nextDay() {
    const d = new Date(date + "T12:00:00");
    d.setDate(d.getDate() + 1);
    setDate(d.toISOString().slice(0, 10));
    setLoading(true);
  }

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 py-4 flex justify-between items-center">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Walix</h1>
            {user && (
              <p className="text-sm text-slate-500">
                {user.name} · {user.role}
              </p>
            )}
          </div>
          <button
            onClick={logout}
            className="text-sm text-slate-600 hover:text-slate-900"
          >
            Cerrar sesión
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-4">
        {/* Date navigation */}
        <div className="flex items-center gap-2">
          <button
            onClick={prevDay}
            disabled={allDates}
            className="p-1.5 rounded-md border border-slate-300 text-slate-600 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed transition"
            aria-label="Día anterior"
          >
            ←
          </button>
          <span className="text-sm font-medium text-slate-700 min-w-[5rem] text-center">
            {allDates ? "Todos" : formatDateLabel(date)}
          </span>
          <button
            onClick={nextDay}
            disabled={allDates || date >= todayStr()}
            className="p-1.5 rounded-md border border-slate-300 text-slate-600 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed transition"
            aria-label="Día siguiente"
          >
            →
          </button>
          <button
            onClick={() => { setAllDates((v) => !v); setLoading(true); }}
            className={`ml-1 px-3 py-1.5 text-sm rounded-full border transition ${
              allDates
                ? "bg-slate-900 text-white border-slate-900"
                : "bg-white border-slate-300 text-slate-600 hover:bg-slate-100"
            }`}
          >
            Todos
          </button>
        </div>

        <div className="flex gap-2 flex-wrap">
          {STATUS_FILTERS.map((s) => {
            const active = filter === s.value;
            return (
              <button
                key={s.value}
                onClick={() => setFilter(s.value)}
                className={`px-3 py-1.5 text-sm rounded-full border transition ${
                  active
                    ? "bg-slate-900 text-white border-slate-900"
                    : "bg-white border-slate-300 text-slate-700 hover:bg-slate-100"
                }`}
              >
                {s.label}
              </button>
            );
          })}
        </div>

        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
            {error}
          </div>
        )}

        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          {loading ? (
            <div className="p-6 text-sm text-slate-500">Cargando leads…</div>
          ) : leads.length === 0 ? (
            <div className="p-6 text-sm text-slate-500">
              No hay leads para mostrar.
            </div>
          ) : (
            <ul className="divide-y divide-slate-200">
              {leads.map((l) => {
                const sm = STATUS_META[l.status];
                const scorePct = l.qualification_score != null
                  ? Math.round(l.qualification_score * 100)
                  : null;
                const barColor =
                  l.qualification_score == null ? "bg-slate-200"
                  : l.qualification_score >= 0.8 ? "bg-emerald-500"
                  : l.qualification_score >= 0.5 ? "bg-amber-400"
                  : "bg-red-400";
                return (
                  <li key={l.id}>
                    <Link
                      href={`/dashboard/leads/${l.id}`}
                      className="flex items-center gap-4 px-4 py-3 hover:bg-slate-50"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-medium truncate">
                          {l.name ?? "(sin nombre)"}
                        </div>
                        <div className="text-sm text-slate-500">{l.wa_phone}</div>
                      </div>
                      <div className="hidden sm:flex flex-col items-end gap-0.5 w-20 shrink-0">
                        <span className="text-xs text-slate-500">
                          {scorePct != null ? `${scorePct}%` : "—"}
                        </span>
                        <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${barColor}`}
                            style={{ width: scorePct != null ? `${scorePct}%` : "0%" }}
                          />
                        </div>
                      </div>
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ring-1 ${sm.cls}`}>
                        {sm.label}
                      </span>
                      <span className="hidden md:block text-sm text-slate-500 w-20 text-right">
                        {sentimentLabel(l.sentiment)}
                      </span>
                      <span className="text-sm text-slate-500 w-16 text-right shrink-0">
                        {formatTime(l.created_at)}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <p className="text-xs text-slate-400">
          Se actualiza automáticamente cada 15 segundos.
        </p>
      </main>
    </div>
  );
}
