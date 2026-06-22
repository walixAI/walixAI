/**
 * tenantUsers — miembros del tenant (para filtro de vendedor y avatares de owner).
 *
 * NOTA (MVP): el modelo Deal de Walix aún NO tiene owner_id, así que los dueños se
 * muestran como "Sin asignar". Este hook intenta leer los usuarios del tenant de
 * /api/users de forma best-effort y degrada a [] si el endpoint no existe todavía.
 * FASE 2: agregar owner_id al Deal y apuntar este hook al endpoint real de usuarios.
 */
import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "./_client";

export interface TenantUser {
  id: string;
  name: string;
  email: string | null;
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
      try {
        const rows = await apiRequest<any[]>("/api/users");
        const arr = Array.isArray(rows) ? rows : (rows as any)?.items ?? [];
        return arr.map((p: any) => {
          const name = p.full_name || p.name || p.email || "Sin nombre";
          return {
            id: p.id,
            name,
            email: p.email ?? null,
            initials: initialsFor(name),
            color: colorForUser(p.id),
            isActive: p.is_active ?? true,
          };
        });
      } catch {
        return []; // FASE 2: endpoint de usuarios del tenant
      }
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
