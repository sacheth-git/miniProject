/** Shared harness for end-to-end tests: the real app (jsdom) against the real API on :8000. */
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";
import { setTokens } from "../lib/session";

export const API = process.env.E2E_API ?? "http://127.0.0.1:8000";
export const E2E = process.env.E2E === "1";
export const realFetch = globalThis.fetch;

/** jsdom's FormData/File can't cross into Node's fetch; encode multipart by hand. */
async function encodeMultipart(fd: FormData): Promise<{ body: Uint8Array; type: string }> {
  const boundary = "----skillmatch" + Math.random().toString(16).slice(2);
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [];
  for (const [name, value] of fd.entries()) {
    if (typeof value === "string") {
      parts.push(enc.encode(`--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`));
    } else {
      const bytes = await new Promise<Uint8Array>((ok, fail) => {
        const r = new FileReader(); // jsdom's reader understands jsdom's File
        r.onload = () => ok(new Uint8Array(r.result as ArrayBuffer));
        r.onerror = () => fail(r.error);
        r.readAsArrayBuffer(value);
      });
      parts.push(enc.encode(`--${boundary}\r\nContent-Disposition: form-data; name="${name}"; filename="${value.name}"\r\nContent-Type: ${value.type || "application/octet-stream"}\r\n\r\n`));
      parts.push(bytes, enc.encode("\r\n"));
    }
  }
  parts.push(enc.encode(`--${boundary}--\r\n`));
  const body = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let off = 0;
  for (const p of parts) {
    body.set(p, off);
    off += p.length;
  }
  return { body, type: `multipart/form-data; boundary=${boundary}` };
}

export function installFetch(): void {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const target = url.startsWith("/api") ? API + url.slice(4) : url;
    if (init?.body instanceof FormData) {
      const { body, type } = await encodeMultipart(init.body);
      const headers = new Headers(init.headers);
      headers.set("Content-Type", type);
      return realFetch(target, { ...init, body, headers });
    }
    return realFetch(target, init);
  });
  window.matchMedia = ((q: string) => ({
    matches: q.includes("min-width"), media: q, addEventListener() {}, removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
}

export interface Session {
  access_token: string;
  refresh_token: string;
  user: { id: string; email: string };
}

export async function api<T>(path: string, init: RequestInit = {}, s?: Session): Promise<T> {
  const headers = new Headers(init.headers);
  if (s) headers.set("Authorization", `Bearer ${s.access_token}`);
  if (init.body && typeof init.body === "string") headers.set("Content-Type", "application/json");
  const r = await realFetch(API + path, { ...init, headers });
  if (!r.ok) throw new Error(`${init.method ?? "GET"} ${path} -> ${r.status} ${await r.text()}`);
  return r.status === 204 ? (undefined as T) : ((await r.json()) as T);
}

/** Render the whole app at `route`, signed in as `s`. */
export function renderAs(s: Session | null, route: string) {
  setTokens(s ? { access_token: s.access_token, refresh_token: s.refresh_token } : null);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
