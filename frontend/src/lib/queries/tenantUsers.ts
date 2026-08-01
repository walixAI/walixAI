import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "./_client";

export interface TenantUser {
  id: string;
  name: string;
  role: string;
  initials: string;
  color: string;
  isActive: boolean;
}

const PALETTE = [
  "hsl(239 84% 60%)",
  "hsl(189 94% 43%)",
  "hsl(38 92% 50%)",
  "hsl(142 71% 45%)",
  "hsl(280 70% 55%)",
  "hsl(0 75% 60%)",
  "hsl(160 70% 45%)",
  "hsl(20 90% 55%)",
];

function hash(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h;
}

export function colorForUser(id: string): string {
  return PALETTE[hash(id) % PALETTE.length];
}

export function initialsFor(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "—";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function useTenantUsers() {
  return useQuery({
    queryKey: ["tenant-users"],
    staleTime: 60_000,
    queryFn: async (): Promise<TenantUser[]> => {
      const rows = await apiRequest<any[]>("/api/users");
      const arr = Array.isArray(rows) ? rows : [];
      return arr.map((p: any) => {
        const name = (p.name || "Sin nombre") as string;
        return {
          id: p.id,
          name,
          role: p.role ?? "",
          initials: initialsFor(name),
          color: colorForUser(p.id),
          isActive: p.is_active ?? true,
        };
      });
    },
  });
}

export function resolveOwner(
  users: TenantUser[] | undefined,
  ownerId: string | null,
): { id: string | null; name: string; initials: string; color: string } {
  if (!ownerId) {
    return { id: null, name: "Sin asignar", initials: "—", color: "hsl(220 13% 65%)" };
  }
  const u = users?.find((x) => x.id === ownerId);
  if (u) return { id: u.id, name: u.name, initials: u.initials, color: u.color };
  return { id: ownerId, name: "Usuario", initials: "·", color: colorForUser(ownerId) };
}
