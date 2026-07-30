import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ContactTabResumen } from "./ContactTabResumen";
import { ContactTabConversaciones } from "./ContactTabConversaciones";
import { ContactTabActividades } from "./ContactTabActividades";
import { TasksTab } from "./TasksTab";
import type { ContactRow } from "@/lib/queries/contacts";
import type { ActivityRow } from "@/lib/queries/activities";

interface ContactTabsProps {
  contact: ContactRow;
  recentActivities: ActivityRow[];
  activitiesTotal: number;
  activitiesLoading: boolean;
  activitiesQueryKey: unknown[];
  activeTab?: string;
  onTabChange?: (tab: string) => void;
}

export function ContactTabs({
  contact,
  recentActivities,
  activitiesTotal,
  activitiesLoading,
  activitiesQueryKey,
  activeTab = "resumen",
  onTabChange,
}: ContactTabsProps) {
  return (
    <Tabs value={activeTab} onValueChange={onTabChange}>
      <TabsList className="w-full justify-start mb-4">
        <TabsTrigger data-testid="tab-resumen" value="resumen">Resumen</TabsTrigger>
        <TabsTrigger data-testid="tab-conversaciones" value="conversaciones">Conversaciones</TabsTrigger>
        <TabsTrigger data-testid="tab-actividades" value="actividades">
          Actividades
          {activitiesTotal > 0 && (
            <span className="ml-1.5 inline-flex items-center justify-center h-4 min-w-[16px] px-1 rounded-full bg-primary/15 text-primary text-[9px] font-bold tabular-nums">
              {activitiesTotal}
            </span>
          )}
        </TabsTrigger>
        <TabsTrigger data-testid="tab-tareas" value="tareas">Tareas</TabsTrigger>
      </TabsList>

      <TabsContent value="resumen" className="mt-0">
        <ContactTabResumen
          contact={contact}
          recentActivities={recentActivities}
          activitiesTotal={activitiesTotal}
          activitiesLoading={activitiesLoading}
          contactId={contact.id}
          activitiesQueryKey={activitiesQueryKey}
          onViewAllActivities={() => onTabChange?.("actividades")}
        />
      </TabsContent>

      <TabsContent value="conversaciones" className="mt-0">
        <ContactTabConversaciones contact={contact} />
      </TabsContent>

      <TabsContent value="actividades" className="mt-0">
        <ContactTabActividades contactId={contact.id} />
      </TabsContent>

      <TabsContent value="tareas" className="mt-0">
        <TasksTab
          contactId={contact.id}
          contactName={`${contact.name ?? ""} ${(contact as any).lastName ?? ""}`.trim() || null}
        />
      </TabsContent>
    </Tabs>
  );
}
