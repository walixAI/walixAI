import { useCallback, useReducer } from "react";
import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import {
  MessageCircle,
  CheckCircle2,
  XCircle,
  ClipboardList,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { OppCard } from "@/lib/api";
import { useOpportunityStore } from "@/stores/opportunityStore";
import { useOpportunityHealth } from "../hooks/useOpportunityHealth";

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatMXN(n: string | number | null | undefined): string {
  if (n === null || n === undefined) return "";
  const val = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(val) || val === 0) return "";
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

function avatarColor(id: string | null | undefined): string {
  const COLORS = [
    "#6B7FFF", "#6ECE58", "#FFB84D", "#FF4242",
    "#4FA8FF", "#2DD4BF", "#A855F7", "#EC4899",
  ];
  if (!id) return COLORS[0];
  let h = 0;
  for (const c of id) h = ((h * 31) + c.charCodeAt(0)) & 0xffffffff;
  return COLORS[Math.abs(h) % COLORS.length];
}

function initials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

function ProbabilityBar({ probability }: { probability: number | null }) {
  if (probability === null) return null;
  const pct = Math.max(0, Math.min(100, probability));
  const colorClass =
    pct >= 70 ? "bg-success" : pct >= 40 ? "bg-warning" : "bg-danger";
  const label =
    pct >= 70
      ? `${pct}% — Alta probabilidad`
      : pct >= 40
      ? `${pct}% — Probabilidad media`
      : `${pct}% — Baja probabilidad`;

  return (
    <div
      className="space-y-0.5"
      title={label}
      aria-label={`Probabilidad de cierre: ${label}`}
    >
      <div className="flex items-center gap-2">
        <div
          className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={cn("h-full rounded-full transition-all", colorClass)}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className={cn("text-[10px] font-semibold tabular-nums", {
          "text-success": pct >= 70,
          "text-warning": pct >= 40 && pct < 70,
          "text-danger": pct < 40,
        })}>
          {pct}%
        </span>
      </div>
    </div>
  );
}

// ── Card content (pure visual, no DnD) ───────────────────────────────────────

export function OpportunityCardContent({
  opp,
  isSelected,
  hasSelection,
  onSelect,
  onClick,
}: {
  opp: OppCard;
  isSelected?: boolean;
  hasSelection?: boolean;
  onSelect?: (id: string) => void;
  onClick?: () => void;
}) {
  const [hovered, toggleHover] = useReducer((s: boolean) => !s, false);
  const health = useOpportunityHealth(opp);
  const { openLostModal, openTaskModal } = useOpportunityStore();
  const showCheckbox = hovered || hasSelection;
  const isTerminal = opp.status === "won" || opp.status === "lost";

  // AI chip uses a neutral info style — urgency duplication removed since
  // health badge on Row 3 already conveys priority status.

  return (
    <div
      className={cn(
        "relative rounded-lg border border-border bg-card px-3 py-2.5 space-y-2 w-full select-none",
        "transition-shadow hover:shadow-sm",
        isTerminal && "opacity-50",
        isSelected && "ring-2 ring-primary",
        onClick && !isTerminal && "cursor-pointer",
      )}
      onMouseEnter={toggleHover}
      onMouseLeave={toggleHover}
      onClick={onClick}
    >
      {/* Pulsing urgency dot */}
      {(opp.urgency_score ?? 0) > 75 && (
        <span
          className="absolute top-2 right-2 h-2 w-2 rounded-full bg-danger motion-safe:animate-pulse"
          aria-label="Urgencia alta"
          aria-hidden="true"
        />
      )}

      {/* Checkbox */}
      {showCheckbox && onSelect && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onSelect(opp.id); }}
          className={cn(
            "absolute top-2 left-2 h-4 w-4 rounded border border-border bg-background",
            "flex items-center justify-center focus-visible:ring-2 focus-visible:ring-primary",
            isSelected && "bg-primary border-primary",
          )}
          aria-label={isSelected ? "Deseleccionar" : "Seleccionar oportunidad"}
          aria-pressed={isSelected}
        >
          {isSelected && (
            <svg viewBox="0 0 12 12" className="h-3 w-3 text-primary-foreground fill-current">
              <polyline points="2,6 5,9 10,3" strokeWidth="1.5" stroke="currentColor" fill="none" />
            </svg>
          )}
        </button>
      )}

      {/* Row 1: title + icons */}
      <div className="flex items-start gap-1.5 pr-4">
        <p
          className={cn(
            "text-sm font-medium leading-snug flex-1",
            "line-clamp-2",
          )}
        >
          {opp.title}
        </p>
        <div className="flex items-center gap-1 shrink-0 mt-0.5">
          {/* Task icon placeholder */}
          <span className="text-[11px] text-muted-foreground" aria-hidden="true">📋</span>
        </div>
      </div>

      {/* Row 2: amount */}
      {opp.amount && parseFloat(opp.amount) > 0 && (
        <div className="flex items-baseline gap-1">
          <span className="text-base font-bold text-success tabular-nums">
            {formatMXN(opp.amount)}
          </span>
          <span className="text-[10px] text-muted-foreground font-normal">MXN</span>
        </div>
      )}

      {/* Row 3: avatar + vendedor + health badge */}
      <div className="flex items-center gap-2">
        {opp.assigned_to_name ? (
          <span
            className="inline-flex items-center justify-center h-6 w-6 rounded-full text-[10px] font-bold shrink-0 text-white"
            style={{ backgroundColor: avatarColor(opp.assigned_to) }}
            aria-label={`Asignado a ${opp.assigned_to_name}`}
          >
            {initials(opp.assigned_to_name)}
          </span>
        ) : (
          <span
            className="inline-flex items-center justify-center h-6 w-6 rounded-full text-[10px] font-bold shrink-0 bg-muted text-muted-foreground"
            aria-label="Sin asignar"
          >
            ?
          </span>
        )}
        <span className="text-[11px] text-muted-foreground truncate flex-1">
          {opp.assigned_to_name ?? "Sin asignar"}
        </span>
        <span
          className={cn(
            "inline-flex items-center gap-0.5 text-[10px] font-medium px-1.5 py-0.5 rounded-full shrink-0",
            health.colorClass,
          )}
          aria-label={`Estado: ${health.label}`}
        >
          <span aria-hidden="true">{health.icon}</span>
          {health.label}
        </span>
      </div>

      {/* Row 4: AI suggestion */}
      {opp.ai_suggestion && (
        <div
          className="flex items-start gap-1.5 text-[11px] rounded-md px-2 py-1.5 border border-primary/20 bg-primary/5 text-primary"
        >
          <span aria-hidden="true">✨</span>
          <p className="line-clamp-2 leading-tight">{opp.ai_suggestion}</p>
        </div>
      )}

      {/* Row 5: probability bar */}
      <ProbabilityBar probability={opp.probability} />

      {/* Hover quick actions (desktop only, non-terminal) */}
      {hovered && !isTerminal && (
        <div
          className="absolute inset-x-0 bottom-0 rounded-b-lg bg-card/95 backdrop-blur-sm border-t border-border"
          aria-label="Acciones rápidas"
        >
          <div className="flex items-center justify-around py-1.5">
            {opp.lead_wa_phone && (
              <button
                type="button"
                onClick={(e) => e.stopPropagation()}
                className="p-1.5 rounded hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-primary"
                aria-label="Abrir WhatsApp"
              >
                <MessageCircle className="h-3.5 w-3.5 text-success" aria-hidden="true" />
              </button>
            )}
            <button
              type="button"
              onClick={(e) => e.stopPropagation()}
              className="p-1.5 rounded hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-primary"
              aria-label="Marcar como ganada"
            >
              <CheckCircle2 className="h-3.5 w-3.5 text-success" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); openLostModal(opp.id); }}
              className="p-1.5 rounded hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-primary"
              aria-label="Marcar como perdida"
            >
              <XCircle className="h-3.5 w-3.5 text-danger" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); openTaskModal(opp.id); }}
              className="p-1.5 rounded hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-primary"
              aria-label="Nueva tarea"
            >
              <ClipboardList className="h-3.5 w-3.5 text-info" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Draggable card ────────────────────────────────────────────────────────────

export function DraggableOppCard({
  opp,
  isSelected,
  hasSelection,
  onSelect,
  onClick,
}: {
  opp: OppCard;
  isSelected?: boolean;
  hasSelection?: boolean;
  onSelect?: (id: string) => void;
  onClick?: () => void;
}) {
  const isTerminal = opp.status === "won" || opp.status === "lost";

  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: opp.id,
    data: { card: opp },
    disabled: isTerminal,
  });

  const prefersReducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const style =
    transform && !prefersReducedMotion
      ? { transform: CSS.Translate.toString(transform) }
      : undefined;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      // Keyboard a11y: Enter/Space opens the detail drawer.
      // Full keyboard DnD (drag-to-stage) requires KeyboardSensor + SortableContext refactor — deferred to Sprint 13.
      // onMouseEnter/Leave don't fire on touch devices so hover quick-actions are inherently touch-safe.
      tabIndex={0}
      role="button"
      aria-label={`Oportunidad: ${opp.title}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick?.();
        }
      }}
      className={cn(
        "touch-none",
        isDragging && "opacity-30",
        isTerminal ? "cursor-default" : "cursor-grab active:cursor-grabbing",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-lg",
      )}
    >
      <OpportunityCardContent
        opp={opp}
        isSelected={isSelected}
        hasSelection={hasSelection}
        onSelect={onSelect}
        onClick={onClick}
      />
    </div>
  );
}
