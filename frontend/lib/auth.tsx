"use client";

// Session context: loads the current profile, exposes login/logout helpers, and
// guards client routes. Tokens are managed by lib/api.

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, clearTokens, getAccess, setTokens } from "./api";
import type { Profile } from "./types";

interface AuthState {
  user: Profile | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    if (!getAccess()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api<Profile>("/api/v1/me");
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async (email: string, password: string) => {
    const data = await api<{ access_token: string; refresh_token: string }>(
      "/api/v1/auth/login",
      { method: "POST", auth: false, body: { email, password } }
    );
    setTokens(data.access_token, data.refresh_token);
    await load();
  };

  const logout = async () => {
    try {
      const refresh = localStorage.getItem("aim_refresh");
      if (refresh)
        await api("/api/v1/auth/logout", {
          method: "POST",
          auth: false,
          body: { refresh_token: refresh },
        });
    } catch {
      /* ignore */
    }
    clearTokens();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, refresh: load, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
