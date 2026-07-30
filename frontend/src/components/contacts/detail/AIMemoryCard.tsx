import { useQuery } from "@tanstack/react-query";
import { Brain } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  contactId: string;
}

export function AIMemoryCard({ contactId }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai-context", "contact", contactId],
    queryFn: () => api.getContactAiContext(contactId),
    staleTime: 60_000,
    retry: false,
  });

  if (isLoading || isError || !data?.context_summary) return null;

  const facts = data.key_facts.slice(0, 5);

  return (
    <div
      className={cn(
        "rounded-xl border border-primary/40 bg-primary/5 p-4 mb-4 flex flex-col gap-2.5",
      )}
    >
      <div className="flex items-start gap-2.5">
        <Brain className="h-4 w-4 text-primary shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-primary">Memoria de IA</span>
          </div>
          <p className="text-sm text-foreground leading-snug">{data.context_summary}</p>
        </div>
      </div>

      {facts.length > 0 && (
        <ul className="pl-7 flex flex-col gap-1">
          {facts.map((fact, i) => (
            <li key={i} className="text-xs text-muted-foreground flex items-start gap-1.5">
              <span className="mt-1 h-1 w-1 rounded-full bg-primary/50 shrink-0" />
              <span>{String(fact)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
