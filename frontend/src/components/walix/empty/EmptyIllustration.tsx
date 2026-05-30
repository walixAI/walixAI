import { cn } from "@/lib/utils";

type Variant = "contacts" | "pipeline" | "whatsapp" | "reports" | "automations";

export function EmptyIllustration({
  variant,
  className,
}: { variant: Variant; className?: string }) {
  const cls = cn("h-32 w-32 text-primary/70", className);

  if (variant === "contacts") {
    return (
      <svg viewBox="0 0 120 120" className={cls} fill="none" aria-hidden="true">
        <circle cx="60" cy="60" r="56" className="fill-primary/5" />
        <circle cx="60" cy="48" r="16" className="fill-primary/30" />
        <path d="M30 96c4-14 16-22 30-22s26 8 30 22" className="stroke-primary/50" strokeWidth="4" strokeLinecap="round" />
        <circle cx="92" cy="36" r="10" className="fill-success/80" />
        <path d="M88 36l3 3 5-6" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  if (variant === "pipeline") {
    return (
      <svg viewBox="0 0 140 100" className={cn("h-28 w-36 text-primary/70", className)} fill="none" aria-hidden="true">
        <rect x="6" y="20" width="36" height="70" rx="6" className="fill-primary/10" />
        <rect x="52" y="20" width="36" height="70" rx="6" className="fill-primary/15" />
        <rect x="98" y="20" width="36" height="70" rx="6" className="fill-primary/20" />
        <rect x="12" y="30" width="24" height="14" rx="3" className="fill-card stroke-primary/40" strokeWidth="1.5" />
        <rect x="58" y="30" width="24" height="14" rx="3" className="fill-card stroke-primary/40" strokeWidth="1.5" />
        <rect x="58" y="50" width="24" height="14" rx="3" className="fill-card stroke-primary/40" strokeWidth="1.5" />
        <rect x="104" y="30" width="24" height="14" rx="3" className="fill-card stroke-primary/40" strokeWidth="1.5" />
      </svg>
    );
  }

  if (variant === "whatsapp") {
    return (
      <svg viewBox="0 0 120 120" className={cls} fill="none" aria-hidden="true">
        <circle cx="60" cy="60" r="50" className="fill-success/10" />
        <path
          d="M60 30c-16 0-29 12-29 27 0 5 2 10 5 14l-3 11 12-3c5 2 10 4 15 4 16 0 29-12 29-27S76 30 60 30z"
          className="fill-success/80"
        />
        <path d="M50 56c1 6 7 12 13 13l5-3c1-1 3-1 4 0l6 3c1 1 1 2 1 3-1 4-5 6-9 6-12 0-25-13-25-25 0-4 2-8 6-9 1 0 2 0 3 1l3 6c1 1 0 3 0 4l-7 1z" fill="white" />
      </svg>
    );
  }

  if (variant === "reports") {
    return (
      <svg viewBox="0 0 120 100" className={cn("h-24 w-32 text-primary/70", className)} fill="none" aria-hidden="true">
        <rect x="4" y="8" width="112" height="84" rx="8" className="fill-card stroke-primary/30" strokeWidth="2" />
        <rect x="20" y="60" width="14" height="20" rx="2" className="fill-primary/40" />
        <rect x="42" y="44" width="14" height="36" rx="2" className="fill-primary/60" />
        <rect x="64" y="32" width="14" height="48" rx="2" className="fill-primary/80" />
        <rect x="86" y="20" width="14" height="60" rx="2" className="fill-primary" />
      </svg>
    );
  }

  // automations
  return (
    <svg viewBox="0 0 120 120" className={cls} fill="none" aria-hidden="true">
      <circle cx="60" cy="60" r="50" className="fill-warning/10" />
      <path
        d="M62 24L36 70h22l-4 26 26-46H58l4-26z"
        className="fill-warning"
        stroke="hsl(var(--warning))"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}
