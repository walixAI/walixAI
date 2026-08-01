import type { MessageOut } from "@/lib/api";

export type WindowTone = "open" | "closing" | "closed";

export interface ServiceWindow {
  open: boolean;
  tone: WindowTone;
  shortLabel: string;
  description: string;
  remainingLabel: string;
}

const WINDOW_MS = 24 * 60 * 60 * 1000;
const CLOSING_THRESHOLD_MS = 3 * 60 * 60 * 1000;

function compute(lastInboundAt: Date | null, noMessages?: boolean): ServiceWindow {
  if (!lastInboundAt) {
    return {
      open: false,
      tone: "closed",
      shortLabel: noMessages ? "Sin mensajes" : "Cerrada",
      description: noMessages
        ? "El cliente aún no ha enviado mensajes"
        : "Ventana de 24 h cerrada · solo plantillas aprobadas",
      remainingLabel: "—",
    };
  }

  const remaining = WINDOW_MS - (Date.now() - lastInboundAt.getTime());

  if (remaining <= 0) {
    return {
      open: false,
      tone: "closed",
      shortLabel: "Cerrada",
      description: "Ventana de 24 h cerrada · solo plantillas aprobadas",
      remainingLabel: "—",
    };
  }

  const hours = Math.floor(remaining / (60 * 60 * 1000));
  const minutes = Math.floor((remaining % (60 * 60 * 1000)) / 60_000);
  const remainingLabel = hours >= 1 ? `${hours} h` : `${minutes} min`;

  if (remaining < CLOSING_THRESHOLD_MS) {
    return {
      open: true,
      tone: "closing",
      shortLabel: remainingLabel,
      description: `Ventana cerrándose · ${remainingLabel} restantes`,
      remainingLabel,
    };
  }

  return {
    open: true,
    tone: "open",
    shortLabel: remainingLabel,
    description: `Ventana abierta · cierra en ${remainingLabel}`,
    remainingLabel,
  };
}

export function getLastInboundAt(messages: MessageOut[]): Date | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") return new Date(messages[i].created_at);
  }
  return null;
}

/** Precise: from conversation messages (use in active-chat context). */
export function getServiceWindowFromMessages(messages: MessageOut[]): ServiceWindow {
  const noMessages = messages.length === 0;
  return compute(getLastInboundAt(messages), noMessages);
}

/**
 * Proxy: from lead.updated_at (list view — no per-lead conversation available).
 * Not perfectly accurate but a safe approximation for the inbox chip.
 */
export function getServiceWindowFromTimestamp(iso: string | null): ServiceWindow {
  return compute(iso ? new Date(iso) : null);
}
