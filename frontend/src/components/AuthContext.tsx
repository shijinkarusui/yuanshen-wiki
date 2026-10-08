import { createContext, useContext } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

interface Me { id: string; display_name: string; kind: string }

const AuthCtx = createContext<{ me: Me | null; loading: boolean }>({ me: null, loading: true });

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return (await api.me()) as Me;
      } catch {
        return null;
      }
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  return <AuthCtx.Provider value={{ me: data ?? null, loading: isLoading }}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  return useContext(AuthCtx);
}
