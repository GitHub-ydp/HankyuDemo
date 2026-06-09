import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { authApi, TOKEN_KEY } from '../services/api';

export interface AuthUser {
  email: string;
  name: string;
  isAdmin: boolean;
  role?: string;
  initial?: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (email: string, password: string, name: string) => Promise<AuthUser>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function initialOf(name: string, email: string) {
  const trimmed = name.trim();
  if (trimmed) {
    const parts = trimmed.split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return trimmed.slice(0, 2).toUpperCase();
  }
  return email.slice(0, 2).toUpperCase();
}

function toUser(raw: { email: string; name: string; is_admin: boolean }): AuthUser {
  return {
    email: raw.email,
    name: raw.name,
    isAdmin: raw.is_admin,
    role: raw.is_admin ? 'ADMIN' : 'OPS MANAGER',
    initial: initialOf(raw.name, raw.email),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  // 初始 loading 由是否存在 token 决定：无 token 直接非加载态，
  // 避免在 effect 内同步调用 setState（触发 react-hooks/set-state-in-effect）
  const [loading, setLoading] = useState(() => !!localStorage.getItem(TOKEN_KEY));

  // 挂载时若有 token → /auth/me 还原会话
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      return;
    }
    authApi
      .me()
      .then((res) => setUser(toUser((res as { data: { email: string; name: string; is_admin: boolean } }).data)))
      .catch(() => localStorage.removeItem(TOKEN_KEY))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback<AuthContextValue['login']>(async (email, password) => {
    const res = await authApi.login(email, password) as { data: { token: string; user: { email: string; name: string; is_admin: boolean } } };
    localStorage.setItem(TOKEN_KEY, res.data.token);
    const u = toUser(res.data.user);
    setUser(u);
    return u;
  }, []);

  const register = useCallback<AuthContextValue['register']>(async (email, password, name) => {
    const res = await authApi.register(email, password, name) as { data: { token: string; user: { email: string; name: string; is_admin: boolean } } };
    localStorage.setItem(TOKEN_KEY, res.data.token);
    const u = toUser(res.data.user);
    setUser(u);
    return u;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
