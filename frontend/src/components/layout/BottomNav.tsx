import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Users, MessageCircle, Kanban,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTenantLabels } from "@/hooks/useTenantLabels";

export function BottomNav() {
  const { entities } = useTenantLabels();
  const items = [
    { to: "/dashboard", label: "Inicio", icon: LayoutDashboard },
    { to: "/whatsapp", label: "WhatsApp", icon: MessageCircle, badge: true },
    { to: "/pipeline", label: "Pipeline", icon: Kanban },
    { to: "/contacts", label: entities, icon: Users },
  ];
  return (
    <nav
      aria-label="Navegacion principal"
      className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-card border-t border-border h-16 grid grid-cols-4 pb-[env(safe-area-inset-bottom)]"
    >
      {items.map(({ to, label, icon: Icon, badge }) => (
        <NavLink
          key={to}
          to={to}
          aria-label={label}
          className={({ isActive }) =>
            cn(
              "relative flex flex-col items-center justify-center gap-1 text-[10px] font-medium transition-colors",
              isActive ? "text-primary" : "text-muted-foreground"
            )
          }
        >
          <Icon className="h-5 w-5" aria-hidden="true" />
          {label}
          {badge && (
            <span
              role="status"
              aria-live="polite"
              className="absolute top-2 right-1/2 translate-x-3 h-2 w-2 rounded-full bg-accent animate-pulse-glow"
            />
          )}
        </NavLink>
      ))}
    </nav>
  );
}
