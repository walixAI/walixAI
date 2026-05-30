import { create } from "zustand";
import { clearToken } from "@/lib/api";
import type { WalixUser } from "@/lib/api";

interface AuthState {
  user: WalixUser | null;
  loading: boolean;
  setUser: (user: WalixUser | null) => void;
  setLoading: (v: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  setUser: (user) => set({ user }),
  setLoading: (loading) => set({ loading }),
  logout: () => {
    clearToken();
    set({ user: null });
  },
}));
