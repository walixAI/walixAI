import { useMemo, useState } from "react";
import { MessageCircle, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { StatusBadge } from "./StatusBadge";
import type { LeadListItem } from "@/lib/api";
import { ConversationListSkeleton } from "@/components/walix/Skeletons";

type Tab = "all" | "bot" | "human" | "calificados";

function timeAgo(iso: string | null) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "ahora";
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h`;
  const days = Math.floor(h / 24);
  if (days < 7) return `${days} d`;
  return new Date(iso).toLocaleDateString("es-MX", { day: "2-digit", month: "short" });
}

function getInitials(name: string | null, phone: string): string {
  if (name) {
    return name
      .split(" ")
      .map((s) => s[0])
      .slice(0, 2)
      .join("")
      .toUpperCase();
  }
  return phone.slice(-2);
}

function getAvatarColor(id: string): string {
  const colors = [
    "hsl(239 84% 67%)",
    "hsl(142 71% 45%)",
    "hsl(346 77% 50%)",
    "hsl(199 89% 48%)",
    "hsl(31 81% 56%)",
    "hsl(270 67% 60%)",
  ];
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = id.charCodeAt(i) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
}

interface Props {
  leads: LeadListItem[];
  activeId: string | null;
  onSelect: (id: string) => void;
  loading?: boolean;
}

export function ConversationList({ leads, activeId, onSelect, loading }: Props) {
  const [tab, setTab] = useState<Tab>("all");
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    let list = leads;
    if (tab === "calificados") list = list.filter((l) => l.status === "calificado");
    // bot/human filtering would need conversation status; for now filter by status
    const lower = q.trim().toLowerCase();
    if (lower) {
      list = list.filter(
        (l) =>
          (l.name ?? "").toLowerCase().includes(lower) ||
          l.wa_phone.includes(lower) ||
          (l.contact_phone ?? "").includes(lower)
      );
    }
    return list;
  }, [leads, tab, q]);

  const tabs: { id: Tab; label: string }[] = [
    { id: "all", label: "Todos" },
    { id: "bot", label: "Bot" },
    { id: "human", label: "Humano" },
    { id: "calificados", label: "Calificados" },
  ];

  return (
    <aside className="w-full md:w-[320px] md:shrink-0 border-r border-border bg-card flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-full bg-success/10 text-success flex items-center justify-center">
            <MessageCircle className="h-4 w-4" />
          </div>
          <h2 className="font-semibold flex-1">WhatsApp</h2>
          <span className="text-xs font-bold bg-primary text-primary-foreground rounded-full px-2 py-0.5">
            {leads.length}
          </span>
        </div>

        {/* Tabs */}
        <div className="mt-3 flex gap-1 bg-muted rounded-lg p-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "flex-1 text-[11px] font-medium px-2 py-1.5 rounded-md transition",
                tab === t.id
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative mt-3">
          <Search className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar nombre o telefono..."
            className="pl-9 h-9 text-sm"
          />
        </div>
      </div>

      {/* List */}
      <ScrollArea className="flex-1">
        {loading && <ConversationListSkeleton rows={8} />}
        {!loading && filtered.length === 0 && (
          <div className="p-6 text-sm text-muted-foreground text-center">Sin leads</div>
        )}
        <ul className="divide-y divide-border">
          {filtered.map((lead) => {
            const active = lead.id === activeId;
            const displayName = lead.name ?? lead.wa_phone;
            const initials = getInitials(lead.name, lead.wa_phone);
            const avatarColor = getAvatarColor(lead.id);
            return (
              <li key={lead.id}>
                <button
                  onClick={() => onSelect(lead.id)}
                  className={cn(
                    "w-full text-left px-4 py-3 flex gap-3 hover:bg-muted/60 transition",
                    active && "bg-primary/5 hover:bg-primary/5"
                  )}
                >
                  {/* Avatar */}
                  <div className="relative shrink-0">
                    <div
                      className="h-10 w-10 rounded-full flex items-center justify-center text-white text-xs font-semibold"
                      style={{ background: avatarColor }}
                    >
                      {initials}
                    </div>
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-sm truncate flex-1">{displayName}</p>
                      <span className="text-[10px] text-muted-foreground shrink-0">
                        {timeAgo(lead.updated_at)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      {lead.wa_phone}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <StatusBadge status={lead.status} />
                      {lead.qualification_score != null && (
                        <span className="text-[10px] text-muted-foreground">
                          Score: {lead.qualification_score}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </ScrollArea>
    </aside>
  );
}
