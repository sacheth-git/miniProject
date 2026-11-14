/**
 * Token storage and refresh. Tokens live in localStorage so a reload keeps you signed
 * in; access tokens are short-lived (30 min) and refreshed transparently on a 401.
 */
const KEY = "skillmatch.session";

export interface Tokens {
  access_token: string;
  refresh_token: string;
}

type Listener = (t: Tokens | null) => void;
const listeners = new Set<Listener>();
let current: Tokens | null = load();

function load(): Tokens | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    return null;
  }
}

export function getTokens(): Tokens | null {
  return current;
}

export function setTokens(t: Tokens | null): void {
  current = t;
  try {
    if (t) localStorage.setItem(KEY, JSON.stringify({ access_token: t.access_token, refresh_token: t.refresh_token }));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: session lasts for this tab only */
  }
  listeners.forEach((l) => l(t));
}

export function onTokens(l: Listener): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

let refreshing: Promise<boolean> | null = null;

/** Exchange the refresh token once; concurrent 401s share one refresh call. */
export function refreshTokens(base: string): Promise<boolean> {
  if (refreshing) return refreshing;
  const t = current;
  if (!t) return Promise.resolve(false);
  refreshing = fetch(`${base}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: t.refresh_token }),
  })
    .then(async (r) => {
      if (!r.ok) {
        setTokens(null);
        return false;
      }
      setTokens(await r.json());
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}
