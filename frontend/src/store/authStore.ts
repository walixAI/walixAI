// Alias de @/store/auth — mantiene compatibilidad con el path del spec Sprint 8B.
// El store real vive en auth.ts; todos los imports apuntan a este archivo o a auth.ts
// indistintamente (misma instancia de Zustand).
export { useAuthStore } from "@/store/auth";
export type { } from "@/store/auth";
