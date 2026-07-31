import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./_client";

export interface Capability {
  id: string;
  name: string;
  description: string | null;
  kind: string;
  recipe_json: { steps: { tool: string; note?: string | null }[] };
  trigger_phrases: string[];
  scope_type: string;
  scope_roles: string[];
  scope_user_ids: string[];
  channels: string[];
  require_confirmation: boolean;
  daily_limit: number | null;
  is_active: boolean;
  created_at: string;
}

export interface BuilderMessage {
  role: "user" | "assistant";
  content: string;
}

export interface BuilderSaveRequest {
  name: string;
  description?: string;
  steps: { tool: string; note?: string }[];
  trigger_phrases: string[];
  scope_type: string;
  scope_roles: string[];
  scope_user_ids: string[];
  channels: string[];
  require_confirmation: boolean;
  daily_limit: number | null;
}

export function useCapabilities() {
  return useQuery({
    queryKey: ["capabilities"],
    queryFn: () => apiRequest<Capability[]>("/api/ai/builder/capabilities"),
    staleTime: 30_000,
  });
}

export function useToggleCapability() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      apiRequest<Capability>(`/api/ai/builder/capabilities/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["capabilities"] }),
  });
}

export function useDeleteCapability() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/api/ai/builder/capabilities/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["capabilities"] }),
  });
}

export function useBuilderChat() {
  return useMutation({
    mutationFn: (messages: BuilderMessage[]) =>
      apiRequest<{ reply: string }>("/api/ai/builder/chat", {
        method: "POST",
        body: JSON.stringify({ messages }),
      }),
  });
}

export function useSaveCapability() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BuilderSaveRequest) =>
      apiRequest<{ id: string }>("/api/ai/builder/save", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["capabilities"] }),
  });
}
