import { create } from "zustand";
import { clearToken } from "@/lib/api";
import type { WalixUser, TenantData } from "@/lib/api";

interface AuthState {
  user: WalixUser | null;
  tenant: TenantData | null;
  loading: boolean;
  // Sprint 8B — campos del Industry Template, expuestos directamente para el hook
  entityName: string;
  entityPlural: string;
  contactStatuses: Array<{ key: string; label: string; color: string }>;
  setUser: (user: WalixUser | null) => void;
  setTenant: (tenant: TenantData | null) => void;
  setEntityName: (v: string) => void;
  setEntityPlural: (v: string) => void;
  setContactStatuses: (v: Array<{ key: string; label: string; color: string }>) => void;
  setLoading: (v: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  tenant: null,
  loading: true,
  entityName: "Contacto",
  entityPlural: "Contactos",
  contactStatuses: [],

  setUser: (user) => set({ user }),

  setTenant: (tenant) =>
    set({
      tenant,
      entityName: tenant?.entity_name || "Contacto",
      entityPlural: tenant?.entity_plural || "Contactos",
      contactStatuses: tenant?.contact_statuses || [],
    }),

  setEntityName: (entityName) => set({ entityName }),
  setEntityPlural: (entityPlural) => set({ entityPlural }),
  setContactStatuses: (contactStatuses) => set({ contactStatuses }),

  setLoading: (loading) => set({ loading }),

  logout: () => {
    clearToken();
    set({
      user: null,
      tenant: null,
      entityName: "Contacto",
      entityPlural: "Contactos",
      contactStatuses: [],
    });
  },
}));
