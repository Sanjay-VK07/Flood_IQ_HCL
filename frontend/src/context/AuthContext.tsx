"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { API_BASE, api, getStoredToken, setStoredToken } from "@/lib/api";
import type { AuthUser, UserRole } from "@/lib/types";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function roleHomePath(role: UserRole): string {
  if (role === "citizen") return "/citizen";
  if (role === "response_team") return "/team";
  return "/";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const token = getStoredToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const res = await api.getMe();
      setUser(res.user);
    } catch {
      setStoredToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    setStoredToken(res.access_token);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(async () => {
    const token = getStoredToken();
    setStoredToken(null);
    setUser(null);
    if (!token) return;
    // Clear the browser session immediately. A slow or unreachable API must not
    // trap the user on a protected portal instead of returning to role selection.
    void fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    }).catch(() => {
      // Local sign-out still succeeds when the API cannot be reached.
    });
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
