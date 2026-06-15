import { useEffect } from "react";
import { useAuthStore } from "@/store/auth";
import { api, getToken } from "@/lib/api";

export function useInitAuth() {
  const { setUser, setTenant, setLoading } = useAuthStore();
  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((data) => {
        setUser(data.user);
        setTenant(data.tenant);
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
