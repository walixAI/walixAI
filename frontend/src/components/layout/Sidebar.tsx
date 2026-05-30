import { NavLink } from "react-router-dom";
import {
  LayoutDashboard, Users, MessageCircle, BarChart3,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/walix/Logo";
import { WBadge } from "@/components/walix/Badge";
import { useState } from "react";

const items = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/whatsapp", label: "WhatsApp", icon: MessageCircle, badge: true },
  { to: "/contacts", label: "Contactos", icon: Users },
  { to: "/reports", label: "Reportes", icon: BarChart3 },
  { to: "/settings", label: "Configuracion", icon: Settings },
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
          {items.map((item) => (
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
  collapsed,
}: {
  to: string;
  label: string;
  icon: React.ElementType;
  badge?: boolean;
  collapsed: boolean;
}) {
  return (
    <NavLink
      to={to}
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
