import { Link } from "react-router-dom";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Clock, MoveRight, FileText, StickyNote, CheckCircle2 } from "lucide-react";
import { useRecentActivity } from "@/lib/queries/dashboard";
import { relativeTime } from "@/lib/format/relativeTime";
import { ListRowsSkeleton } from "@/components/walix/Skeletons";
import { cn } from "@/lib/utils";

const activityIcon: Record<string, { icon: typeof MoveRight; color: string }> = {
  deal:        { icon: MoveRight,    color: "text-primary bg-primary/10" },
  wa_sent:     { icon: FileText,     color: "text-accent bg-accent/10" },
  wa_received: { icon: FileText,     color: "text-success bg-success/10" },
  note:        { icon: StickyNote,   color: "text-warning bg-warning/10" },
  task:        { icon: CheckCircle2, color: "text-success bg-success/10" },
};

export function RecentActivityCard() {
  const { data: activity = [], isLoading: activityLoading } = useRecentActivity(10);

  return (
    <div className="rounded-xl border border-border bg-card shadow-card">
      <div className="flex items-center justify-between p-5 border-b border-border">
        <div>
          <h3 className="font-semibold">Actividad Reciente</h3>
          <p className="text-xs text-muted-foreground">Últimas acciones de tu equipo</p>
        </div>
        <Button variant="ghost" size="sm" className="text-primary">Ver todo</Button>
      </div>
      <div className="divide-y divide-border">
        {activityLoading && activity.length === 0 ? (
          <ListRowsSkeleton rows={5} />
        ) : (
          <>
            {activity.map((a) => {
              const meta = activityIcon[a.type] ?? activityIcon.note;
              const ActIcon = meta.icon;
              return (
                <div key={a.id} className="flex items-center gap-3 px-5 py-3 hover:bg-muted/50 transition-colors">
                  <Avatar className="h-9 w-9">
                    <AvatarFallback className="bg-gradient-brand text-primary-foreground text-xs font-semibold">
                      {a.contactName ? a.contactName.split(" ").map((s) => s[0]).slice(0, 2).join("") : "•"}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0 text-sm">
                    <p className="truncate">
                      <span className="text-muted-foreground">{a.description}</span>
                      {a.contactName && (
                        <>
                          {" · "}
                          {a.contactId ? (
                            <Link to={`/contacts/${a.contactId}`} className="font-medium text-foreground hover:text-primary">
                              {a.contactName}
                            </Link>
                          ) : (
                            <span className="font-medium text-foreground">{a.contactName}</span>
                          )}
                        </>
                      )}
                    </p>
                    <div className="flex items-center gap-1 text-[11px] text-muted-foreground mt-0.5">
                      <Clock className="h-3 w-3" /> {relativeTime(a.occurredAt)}
                    </div>
                  </div>
                  <div className={cn("h-7 w-7 grid place-items-center rounded-lg shrink-0", meta.color)}>
                    <ActIcon className="h-3.5 w-3.5" />
                  </div>
                </div>
              );
            })}
            {activity.length === 0 && (
              <div className="px-5 py-8 text-center text-sm text-muted-foreground">Sin actividad reciente.</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
