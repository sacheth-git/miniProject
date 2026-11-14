import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type RegisterBody, type TokenResponse, type User } from "./api";
import { getTokens, onTokens, setTokens } from "./session";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (body: RegisterBody) => Promise<User>;
  logout: () => Promise<void>;
  acceptTokens: (t: TokenResponse) => void;
  refreshUser: () => void;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [signedIn, setSignedIn] = useState(() => !!getTokens());

  useEffect(
    () =>
      onTokens((t) => {
        setSignedIn(!!t);
        if (!t) qc.clear();
      }),
    [qc],
  );

  const me = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    enabled: signedIn,
    retry: (n, e) => !(e instanceof ApiError && e.status === 401) && n < 1,
    staleTime: 60_000,
  });
  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) setTokens(null);
  }, [me.error]);

  const acceptTokens = useCallback(
    (t: TokenResponse) => {
      setTokens({ access_token: t.access_token, refresh_token: t.refresh_token });
      qc.setQueryData(["me"], t.user);
    },
    [qc],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const t = await api.login(email, password);
      acceptTokens(t);
      return t.user;
    },
    [acceptTokens],
  );
  const register = useCallback(
    async (body: RegisterBody) => {
      const t = await api.register(body);
      acceptTokens(t);
      return t.user;
    },
    [acceptTokens],
  );
  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* already signed out server-side */
    }
    setTokens(null);
  }, []);

  const value = useMemo(
    () => ({
      user: signedIn ? (me.data ?? null) : null,
      loading: signedIn && me.isLoading,
      login,
      register,
      logout,
      acceptTokens,
      refreshUser: () => qc.invalidateQueries({ queryKey: ["me"] }),
    }),
    [signedIn, me.data, me.isLoading, login, register, logout, acceptTokens, qc],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

export const isSeeker = (u: User | null) => !!u && (u.role === "student" || u.role === "job_seeker");
export function homeFor(u: User | null): string {
  if (!u) return "/";
  if (u.must_reset_password) return "/change-password";
  return u.role === "tpo" ? "/tpo" : "/";
}
