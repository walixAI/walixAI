import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Kanban, Users, MessageCircle, BarChart3,
  Settings, Zap, TrendingUp, BarChart2, ClipboardList,
} from "lucide-react";
import {
  CommandDialog, CommandEmpty, CommandGroup,
  CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { useTenantLabels } from "@/hooks/useTenantLabels";
import { useAuth } from "@/hooks/useAuth";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const { entities, deals } = useTenantLabels();
  const { user } = useAuth();

  const isOwner = user?.role === "owner" || user?.role === "platform_owner";
  const roiVisible = isOwner || user?.role === "gerente" || user?.role === "doctor";

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "j") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function go(path: string) {
    setOpen(false);
    navigate(path);
  }

  const navItems = [
    { label: "Dashboard",         path: "/dashboard",    icon: LayoutDashboard },
    { label: "Mi Día",            path: "/mi-dia",       icon: ClipboardList },
    { label: deals,               path: "/pipeline",     icon: Kanban },
    { label: entities,            path: "/contacts",     icon: Users },
    { label: "WhatsApp",          path: "/whatsapp",     icon: MessageCircle },
    { label: "Reportes",          path: "/reports",      icon: BarChart3 },
    { label: "Automatizaciones",  path: "/automations",  icon: Zap },
    { label: "Forecast",          path: "/forecast",     icon: TrendingUp },
    { label: "Configuración",     path: "/settings",     icon: Settings },
    ...(roiVisible ? [{ label: "ROI", path: "/roi", icon: BarChart2 }] : []),
  ];

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Ir a…" />
      <CommandList>
        <CommandEmpty>Sin resultados.</CommandEmpty>
        <CommandGroup heading="Navegación">
          {navItems.map((item) => (
            <CommandItem key={item.path} onSelect={() => go(item.path)}>
              <item.icon className="mr-2 h-4 w-4" />
              {item.label}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
