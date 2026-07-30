import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Users, Users2, MessageCircle, BarChart3,
  Settings, Kanban, TrendingUp, Zap, CreditCard, BarChart2, Bot, BookOpen, ClipboardList, ListTodo,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/walix/Logo";
import { WBadge } from "@/components/walix/Badge";
import { useState } from "react";
import { useTenantLabels } from "@/hooks/useTenantLabels";
import { useAuth } from "@/hooks/useAuth";

export function Sidebar() {
  const [hovered, setHovered] = useState(false);
  const { entities } = useTenantLabels();
  const { user } = useAuth();
  const location = useLocation();
  const isOwner = user?.role === "owner" || user?.role === "platform_owner";
  const canManageBot = isOwner || user?.role === "gerente" || user?.role === "it";

  const roiVisible = isOwner || user?.role === "gerente" || user?.role === "doctor";

  const MAIN_ITEMS = [
    { to: "/dashboard",   label: "Dashboard",       icon: LayoutDashboard },
    { to: "/mi-dia",      label: "Mi Día",           icon: ClipboardList },
    { to: "/tasks",       label: "Tareas",           icon: ListTodo },
    ...(roiVisible ? [{ to: "/roi", label: "ROI", icon: BarChart2 }] : []),
    { to: "/pipeline",    label: "Pipeline",         icon: Kanban },
    { to: "/contacts",    label: entities,            icon: Users },
    { to: "/forecast",    label: "Forecast",         icon: TrendingUp },
    { to: "/automations", label: "Automatizaciones", icon: Zap },
    { to: "/whatsapp",    label: "WhatsApp",         icon: MessageCircle, badge: true },
    { to: "/reports",     label: "Reportes",         icon: BarChart3 },
  ];
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

          {[
            { to: "/settings?tab=bot",       label: "Bot IA",              icon: Bot,      showIf: canManageBot },
            { to: "/settings?tab=kb",        label: "Base de conocimiento", icon: BookOpen, showIf: canManageBot },
            { to: "/settings?tab=whatsapp",  label: "WhatsApp / Meta",     icon: Zap,      showIf: canManageBot },
            { to: "/settings/team",          label: "Equipo",               icon: Users2,   showIf: true },
            ...(isOwner ? [{ to: "/billing", label: "Facturación", icon: CreditCard, showIf: true }] : []),
          ]
            .filter((item) => item.showIf)
            .map((item) => (
              <SettingsNavItem key={item.to} to={item.to} label={item.label} icon={item.icon} collapsed={collapsed} />
            ))}
        </nav>
      </aside>
    </div>
  );
}

// For settings tabs: matches by ?tab= query param
function SettingsNavItem({
  to,
  label,
  icon: Icon,
  collapsed,
}: {
  to: string;
  label: string;
  icon: React.ElementType;
  collapsed: boolean;
}) {
  const location = useLocation();
  // e.g. to="/settings?tab=bot"  → check if current ?tab matches
  const [path, qs] = to.split("?");
  const tabParam = qs ? new URLSearchParams(qs).get("tab") : null;
  const currentTab = new URLSearchParams(location.search).get("tab") ?? "bot";
  const isActive = location.pathname === path && (tabParam === null || currentTab === tabParam)
    || (to === "/settings/team" && location.pathname === "/settings/team")
    || (to === "/billing" && location.pathname === "/billing");

  return (
    <NavLink
      to={to}
      title={collapsed ? label : undefined}
      aria-label={label}
      className={cn(
        "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
        collapsed && "justify-center px-0",
        isActive
          ? "bg-primary text-primary-foreground shadow-glow"
          : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
      )}
    >
      <Icon className="h-[18px] w-[18px] shrink-0" />
      {!collapsed && <span className="flex-1 truncate">{label}</span>}
    </NavLink>
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
      data-tour={`nav-${to.replace(/^\//, "")}`}
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
