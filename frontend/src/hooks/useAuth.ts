import { useEffect } from "react";
import { useAuthStore } from "@/store/auth";
import { api, getToken } from "@/lib/api";

export function useInitAuth() {
  const { setUser, setLoading } = useAuthStore();
  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((u) => {
        setUser(u);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}

export function useAuth() {
  return useAuthStore();
}
