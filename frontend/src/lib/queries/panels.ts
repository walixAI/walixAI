import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "./_client";

export interface PanelOut {
  id: string;
  key: string;
  name: string;
  icon: string | null;
  min_role: string | null;
  is_system: boolean;
  position: number;
  created_by: string | null;
}

export function usePanels() {
  return useQuery({
    queryKey: ["dashboard-panels"],
    queryFn: () => apiRequest<PanelOut[]>("/api/dashboard/panels"),
    staleTime: 60_000,
  });
}

export function useCreatePanel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; icon?: string | null }) =>
      apiRequest<PanelOut>("/api/dashboard/panels", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard-panels"] }),
  });
}

export function useDeletePanel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiRequest<void>(`/api/dashboard/panels/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboard-panels"] }),
  });
}
