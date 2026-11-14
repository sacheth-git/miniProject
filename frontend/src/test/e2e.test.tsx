/**
 * End-to-end: the real React app against the real backend (no mocks).
 * Run with the API on :8000:   $env:E2E="1"; npx vitest run src/test/e2e.test.tsx
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterAll, beforeAll, expect, test, vi } from "vitest";
import App from "../App";
import { getTokens } from "../lib/session";

const API = process.env.E2E_API ?? "http://127.0.0.1:8000";
const run = process.env.E2E === "1" ? test : test.skip;
const realFetch = globalThis.fetch;
let candidateId: string | null = null;

/** jsdom's FormData/File can't cross into Node's fetch; encode multipart by hand (harness only). */
async function encodeMultipart(fd: FormData): Promise<{ body: Uint8Array; type: string }> {
  const boundary = "----skillmatch" + Math.random().toString(16).slice(2);
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [];
  for (const [name, value] of fd.entries()) {
    if (typeof value === "string") {
      parts.push(enc.encode(`--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`));
    } else {
      const bytes = await new Promise<Uint8Array>((ok, fail) => {
        const r = new FileReader(); // jsdom's own reader understands jsdom's File
        r.onload = () => ok(new Uint8Array(r.result as ArrayBuffer));
        r.onerror = () => fail(r.error);
        r.readAsArrayBuffer(value);
      });
      parts.push(enc.encode(`--${boundary}\r\nContent-Disposition: form-data; name="${name}"; filename="${value.name}"\r\nContent-Type: ${value.type || "application/octet-stream"}\r\n\r\n`));
      parts.push(bytes, enc.encode("\r\n"));
    }
  }
  parts.push(enc.encode(`--${boundary}--\r\n`));
  const total = parts.reduce((n, p) => n + p.length, 0);
  const body = new Uint8Array(total);
  let off = 0;
  for (const p of parts) {
    body.set(p, off);
    off += p.length;
  }
  return { body, type: `multipart/form-data; boundary=${boundary}` };
}

beforeAll(() => {
  // The app calls /api/... (Vite proxy in dev); point it at the backend directly.
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const target = url.startsWith("/api") ? API + url.slice(4) : url;
    if (init?.body instanceof FormData) {
      const { body, type } = await encodeMultipart(init.body);
      const headers = new Headers(init.headers); // keep Authorization
      headers.set("Content-Type", type);
      return realFetch(target, { ...init, body, headers });
    }
    return realFetch(target, init);
  });
  window.matchMedia = ((q: string) => ({
    matches: q.includes("min-width"), media: q, addEventListener() {}, removeEventListener() {},
  })) as unknown as typeof window.matchMedia;
});

afterAll(async () => {
  const t = getTokens();
  if (t) await realFetch(`${API}/auth/me`, { method: "DELETE", headers: { Authorization: `Bearer ${t.access_token}` } });
  vi.restoreAllMocks();
});

run(
  "upload -> results -> apply opens the job's exact URL -> tracker",
  async () => {
    localStorage.clear();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/register"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // 0. Sign up through the real onboarding: "Are you a campus student?" -> No.
    fireEvent.click(await screen.findByRole("button", { name: /No, I'm looking for jobs on my own/ }));
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "E2E Tester" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: `e2e-${Date.now()}@test.example` } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "e2e-passw0rd" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    // 1. Upload the sample resume.
    const pdf = readFileSync(resolve(__dirname, "../../../backend/data/samples/uday_ml.pdf"));
    const file = new File([pdf], "uday_ml.pdf", { type: "application/pdf" });
    fireEvent.change(await screen.findByLabelText("Resume PDF", {}, { timeout: 10_000 }), { target: { files: [file] } });
    fireEvent.click(await screen.findByRole("button", { name: "Review my profile" }, { timeout: 60_000 }));
    const authed = { headers: { Authorization: `Bearer ${getTokens()!.access_token}` } };
    candidateId = (await (await realFetch(`${API}/resume/me`, authed)).json()).id;
    expect(candidateId).toBeTruthy();

    // 2. Profile shows extracted skills; go to results.
    expect(await screen.findByRole("button", { name: "Remove PyTorch" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "See matching jobs" }));
    const results = await screen.findByRole("region", { name: "Job results" }, { timeout: 30_000 });
    const cards = await within(results).findAllByRole("article", {}, { timeout: 30_000 });
    expect(cards.length).toBeGreaterThan(5);
    const first = cards[0];
    const pctLabel = within(first).getByRole("img").getAttribute("aria-label");
    console.log("top result:", within(first).getAllByRole("button")[0].textContent, "|", pctLabel);

    // 3. Apply: must open exactly one of that job's apply URLs, in a new tab.
    const job = await (await realFetch(`${API}/match/${candidateId}?limit=1`, authed)).json();
    const urls: string[] = job.items[0].job.apply_options.map((o: { url: string }) => o.url);
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const applyBtn = within(first).getByRole("button", { name: /^apply/i });
    fireEvent.click(applyBtn);
    const item = within(first).queryAllByRole("menuitem")[0];
    if (item) fireEvent.click(item);
    expect(open).toHaveBeenCalledTimes(1);
    const [openedUrl, target, features] = open.mock.calls[0];
    expect(urls).toContain(openedUrl);
    expect(target).toBe("_blank");
    expect(features).toContain("noopener");
    console.log("apply opened:", openedUrl);

    // 4. Coming back to the tab asks "Did you apply?"; confirm.
    await new Promise((r) => setTimeout(r, 1600));
    fireEvent.focus(window);
    fireEvent.click(await screen.findByRole("button", { name: "Yes, mark applied" }));

    // 5. Tracker shows it under Applied.
    await waitFor(async () => {
      const apps = await (await realFetch(`${API}/applications?candidate_id=${candidateId}`, authed)).json();
      expect(apps).toHaveLength(1);
      expect(apps[0].status).toBe("Applied");
      expect(urls).toContain(apps[0].apply_url);
    });
    fireEvent.click(screen.getAllByRole("link", { name: /^Applications/ })[0]);
    const applied = await screen.findByRole("region", { name: /^Applied \(1\)/ }, { timeout: 10_000 });
    expect(within(applied).getAllByRole("article")).toHaveLength(1);
  },
  120_000,
);
