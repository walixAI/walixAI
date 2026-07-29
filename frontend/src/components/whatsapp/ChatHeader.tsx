import { useState } from "react";
import { ChevronRight, Bot, UserCheck, UserMinus, User, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { StatusBadge } from "./StatusBadge";
import { AiSummaryDialog } from "./AiSummaryDialog";
import type { LeadDetail, ConversationOut, UserBrief } from "@/lib/api";

interface Props {
  lead: LeadDetail;
  conversation: ConversationOut | null;
  panelOpen: boolean;
  onTogglePanel: () => void;
  onHandoff: () => void;
  onReturnToBot: () => void;
  onAssign: (userId: string) => void;
  assignees: UserBrief[];
  loadingAction?: boolean;
}

export function ChatHeader({
  lead,
  conversation,
  panelOpen,
  onTogglePanel,
  onHandoff,
  onReturnToBot,
  onAssign,
  assignees,
  loadingAction,
}: Props) {
  const [summaryOpen, setSummaryOpen] = useState(false);
  const displayName = lead.name ?? lead.wa_phone;
  const isHandedOff = conversation?.current_handler === "human";
  const conversationId = conversation?.conversation_id ?? null;

  return (
    <div className="border-b border-border bg-card px-4 py-3 flex items-center gap-3">
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className="min-w-0">
          <p className="font-semibold text-sm truncate">{displayName}</p>
          <p className="text-xs text-muted-foreground truncate">{lead.wa_phone}</p>
        </div>
        <StatusBadge status={lead.status} />
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        {/* AI summary */}
        {conversationId && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-primary hover:text-primary/80 hover:bg-primary/10"
            onClick={() => setSummaryOpen(true)}
            title="Resumen IA"
          >
            <Sparkles className="h-4 w-4" />
          </Button>
        )}

        {/* Handoff controls */}
        {!isHandedOff ? (
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs gap-1.5 border-warning/50 text-warning hover:bg-warning/10"
            onClick={onHandoff}
            disabled={loadingAction}
          >
            <UserCheck className="h-3.5 w-3.5" />
            Tomar control
          </Button>
        ) : (
          <>
            {/* Assign to doctor */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs gap-1.5 border-info/50 text-info hover:bg-info/10"
                  disabled={loadingAction}
                >
                  <User className="h-3.5 w-3.5" />
                  Asignar
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel className="text-xs">Asignar a</DropdownMenuLabel>
                {assignees.length === 0 && (
                  <DropdownMenuItem disabled>Sin usuarios disponibles</DropdownMenuItem>
                )}
                {assignees.map((a) => (
                  <DropdownMenuItem key={a.id} onClick={() => onAssign(a.id)}>
                    {a.name} — {a.role}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Return to bot */}
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs gap-1.5"
              onClick={onReturnToBot}
              disabled={loadingAction}
            >
              <Bot className="h-3.5 w-3.5" />
              Devolver al bot
            </Button>
          </>
        )}

        {/* Assigned to label */}
        {lead.assigned_to_name && (
          <span className="text-xs text-muted-foreground hidden lg:inline">
            <UserMinus className="h-3 w-3 inline mr-0.5" />
            {lead.assigned_to_name}
          </span>
        )}

        {/* Toggle side panel */}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onTogglePanel}
          title={panelOpen ? "Ocultar panel" : "Mostrar panel"}
        >
          <ChevronRight className={`h-4 w-4 transition ${panelOpen ? "rotate-180" : ""}`} />
        </Button>
      </div>

      {conversationId && (
        <AiSummaryDialog
          open={summaryOpen}
          onOpenChange={setSummaryOpen}
          conversationId={conversationId}
          contactId={lead.id}
        />
      )}
    </div>
  );
}
