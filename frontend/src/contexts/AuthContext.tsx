import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

// 最小可用的本地注册 / 登录：把用户信息落到 localStorage，下一步接后端 /auth/* 时只改这个文件即可
export interface AuthUser {
  email: string;
  name: string;
  role?: string;
  initial?: string;
}

interface StoredUser extends AuthUser {
  passwordHash: string;
  createdAt: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  login: (email: string, password: string) => Promise<AuthUser>;
  register: (email: string, password: string, name: string) => Promise<AuthUser>;
  logout: () => void;
}

const USERS_KEY = 'hhrh_users';
const SESSION_KEY = 'hhrh_session';

const AuthContext = createContext<AuthContextValue | null>(null);

// 非加密的简单哈希，仅用于本地演示账号 — 上线前换成后端 bcrypt
function hash(input: string): string {
  let h = 5381;
  for (let i = 0; i < input.length; i += 1) {
    h = ((h << 5) + h) ^ input.charCodeAt(i);
  }
  return (h >>> 0).toString(36);
}

function readUsers(): StoredUser[] {
  try {
    const raw = localStorage.getItem(USERS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeUsers(users: StoredUser[]) {
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

function readSession(): AuthUser | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

function initialOf(name: string, email: string) {
  const trimmed = name.trim();
  if (trimmed) {
    const parts = trimmed.split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return trimmed.slice(0, 2).toUpperCase();
  }
  return email.slice(0, 2).toUpperCase();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => readSession());

  useEffect(() => {
    if (user) {
      localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(SESSION_KEY);
    }
  }, [user]);

  const login = useCallback<AuthContextValue['login']>(async (email, password) => {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail || !password) {
      throw new Error('请填写邮箱和密码');
    }
    const users = readUsers();
    const match = users.find((u) => u.email === normalizedEmail);
    if (!match) throw new Error('账号不存在，请先注册');
    if (match.passwordHash !== hash(password)) throw new Error('密码错误');
    const session: AuthUser = {
      email: match.email,
      name: match.name,
      role: match.role,
      initial: match.initial,
    };
    setUser(session);
    return session;
  }, []);

  const register = useCallback<AuthContextValue['register']>(async (email, password, name) => {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail || !password || !name.trim()) {
      throw new Error('请填写完整的注册信息');
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      throw new Error('邮箱格式不正确');
    }
    if (password.length < 6) {
      throw new Error('密码至少需要 6 位');
    }
    const users = readUsers();
    if (users.some((u) => u.email === normalizedEmail)) {
      throw new Error('该邮箱已注册');
    }
    const record: StoredUser = {
      email: normalizedEmail,
      name: name.trim(),
      role: 'OPS MANAGER',
      initial: initialOf(name, normalizedEmail),
      passwordHash: hash(password),
      createdAt: new Date().toISOString(),
    };
    writeUsers([...users, record]);
    const session: AuthUser = {
      email: record.email,
      name: record.name,
      role: record.role,
      initial: record.initial,
    };
    setUser(session);
    return session;
  }, []);

  const logout = useCallback(() => {
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, login, register, logout }), [user, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
