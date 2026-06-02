import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Users, Users2, MessageCircle, BarChart3,
  Settings, Kanban, TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/walix/Logo";
import { WBadge } from "@/components/walix/Badge";
import { useState } from "react";

const MAIN_ITEMS = [
  { to: "/dashboard",  label: "Dashboard",   icon: LayoutDashboard },
  { to: "/pipeline",   label: "Pipeline",     icon: Kanban },
  { to: "/forecast",   label: "Forecast",     icon: TrendingUp },
  { to: "/whatsapp",   label: "WhatsApp",     icon: MessageCircle, badge: true },
  { to: "/contacts",   label: "Contactos",    icon: Users },
  { to: "/reports",    label: "Reportes",     icon: BarChart3 },
];

const CONFIG_ITEMS = [
  { to: "/settings",      label: "Configuracion", icon: Settings, end: true },
  { to: "/settings/team", label: "Equipo",         icon: Users2 },
];

export function Sidebar() {
  const [hovered, setHovered] = useState(false);
  const expanded = hovered;
  const collapsed = !expanded;

  return (
    <div className="hidden md:block w-16 shrink-0 sticky top-0 h-screen z-40">
      <aside
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className={cn(
          "flex flex-col border-r border-sidebar-border bg-sidebar h-screen transition-[width] duration-200 ease-out",
          expanded ? "w-60 shadow-xl" : "w-16"
        )}
      >
        <div
          className={cn(
            "h-16 flex items-center border-b border-sidebar-border",
            collapsed ? "justify-center" : "px-5"
          )}
        >
          <Logo collapsed={collapsed} />
        </div>

        <nav className="flex-1 overflow-y-auto overflow-x-hidden py-4 px-2 space-y-0.5">
          {MAIN_ITEMS.map((item) => (
            <NavItem key={item.to} {...item} collapsed={collapsed} />
          ))}

          {/* Config section */}
          <div
            className={cn(
              "mt-3 mb-1",
              collapsed
                ? "border-t border-sidebar-border mx-1 pt-3"
                : "pt-3 pb-0.5 px-1",
            )}
          >
            {!collapsed && (
              <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50 px-2">
                Configuración
              </p>
            )}
          </div>

          {CONFIG_ITEMS.map((item) => (
            <NavItem key={item.to} {...item} collapsed={collapsed} />
          ))}
        </nav>
      </aside>
    </div>
  );
}

function NavItem({
  to,
  label,
  icon: Icon,
  badge,
  end,
  collapsed,
}: {
  to: string;
  label: string;
  icon: React.ElementType;
  badge?: boolean;
  end?: boolean;
  collapsed: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      title={collapsed ? label : undefined}
      aria-label={label}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
          collapsed && "justify-center px-0",
          isActive
            ? "bg-primary text-primary-foreground shadow-glow"
            : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        )
      }
    >
      <Icon className="h-[18px] w-[18px] shrink-0" />
      {!collapsed && <span className="flex-1 truncate">{label}</span>}
      {!collapsed && badge && <WBadge variant="brand">nuevo</WBadge>}
      {collapsed && badge && (
        <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-accent animate-pulse-glow" />
      )}
    </NavLink>
  );
}
