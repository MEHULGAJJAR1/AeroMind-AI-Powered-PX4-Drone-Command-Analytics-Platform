import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import type { User } from '../types';

interface AuthContextValue {
  user: User | null;
  token: string | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const TOKEN_KEY = 'aeromind.accessToken';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => window.localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let live = true;
    if (!token) {
      setUser(null);
      setReady(true);
      return () => { live = false; };
    }
    setReady(false);
    api.me()
      .then((current) => { if (live) setUser(current); })
      .catch(() => {
        window.localStorage.removeItem(TOKEN_KEY);
        if (live) { setToken(null); setUser(null); }
      })
      .finally(() => { if (live) setReady(true); });
    return () => { live = false; };
  }, [token]);

  const accept = useCallback((result: Awaited<ReturnType<typeof api.login>>) => {
    window.localStorage.setItem(TOKEN_KEY, result.access_token);
    setToken(result.access_token);
    setUser(result.user);
    setReady(true);
  }, []);

  const login = useCallback(async (email: string, password: string) => accept(await api.login(email, password)), [accept]);
  const register = useCallback(async (email: string, password: string) => accept(await api.register(email, password)), [accept]);
  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
    setReady(true);
  }, []);

  const value = useMemo(() => ({ user, token, ready, login, register, logout }), [user, token, ready, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used within AuthProvider');
  return value;
}
