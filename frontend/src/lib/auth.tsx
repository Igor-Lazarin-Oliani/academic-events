import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, getToken, setToken } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (data: { name: string; email: string; password: string; course?: string }) => Promise<User>;
  logout: () => void;
  isManager: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!getToken());
  const qc = useQueryClient();

  useEffect(() => {
    if (!getToken()) return;
    api<User>("/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ access_token: string; user: User }>("/auth/login", { body: { email, password } });
    setToken(r.access_token);
    qc.clear();
    setUser(r.user);
    return r.user;
  }, [qc]);

  const register = useCallback(async (data: { name: string; email: string; password: string; course?: string }) => {
    const r = await api<{ access_token: string; user: User }>("/auth/register", { body: data });
    setToken(r.access_token);
    qc.clear();
    setUser(r.user);
    return r.user;
  }, [qc]);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    qc.clear();
  }, [qc]);

  const isManager = !!user && ["organizer", "admin", "staff"].includes(user.role);
  return <AuthContext.Provider value={{ user, loading, login, register, logout, isManager }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
