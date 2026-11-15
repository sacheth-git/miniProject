/**
 * End-to-end on the seeded demo campus (run scripts/seed_demo.py first, API on :8000):
 * dashboard KPIs, analytics (heatmap, fairness, unplaced), share link created in the UI and opened publicly.
 *   $env:E2E="1"; npx vitest run src/test/e2e_analytics.test.tsx
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterAll, beforeAll, expect, test, vi } from "vitest";
import { api, E2E, installFetch, renderAs, type Session } from "./e2eHarness";

const run = E2E ? test : test.skip;
beforeAll(() => {
  installFetch();
  // Recharts' ResponsiveContainer needs a size in jsdom.
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
});
afterAll(() => vi.restoreAllMocks());

run("TPO dashboard, analytics and a recruiter share link on the demo campus", async () => {
  const tpo = await api<Session>("/auth/login", { method: "POST", body: JSON.stringify({ email: "tpo@demo.skillmatch.example", password: "Demo@2026" }) });
  const summary = await api<{ placed_pct: number; students: number }>("/tpo/analytics/summary", {}, tpo);

  // Dashboard
  let view = renderAs(tpo, "/tpo");
  await screen.findByRole("heading", { name: "Placement dashboard" }, { timeout: 20_000 });
  expect(screen.getByText(`${summary.placed_pct}%`)).toBeInTheDocument();
  const branchCard = screen.getByRole("region", { name: "Placed by branch" });
  fireEvent.click(within(branchCard).getByRole("tab", { name: "Table" }));
  expect(within(branchCard).getByRole("columnheader", { name: "Placed %" })).toBeInTheDocument();
  expect(within(branchCard).getAllByRole("row").length).toBe(6); // header + 5 branches
  view.unmount();

  // Analytics
  view = renderAs(tpo, "/tpo/analytics");
  await screen.findByRole("heading", { name: "Placement analytics" });
  const heat = await screen.findByRole("table", { name: /missing each demanded skill/ }, { timeout: 30_000 });
  expect(within(heat).getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["CSE", "ECE", "EEE", "IT", "MECH"]);
  await screen.findByRole("heading", { name: "Training recommendations" });
  expect(await screen.findAllByText(/Parity, system:/, {}, { timeout: 20_000 })).toHaveLength(2); // gender + branch
  await screen.findByRole("table", { name: "Unplaced students" }, { timeout: 30_000 });
  view.unmount();

  // Share link from the drive's Export tab, then the public page.
  const drives = await api<{ id: string; company: string }[]>("/tpo/drives", {}, tpo);
  const kaveri = drives.find((d) => d.company === "Kaveri Systems")!;
  view = renderAs(tpo, `/tpo/drives/${kaveri.id}`);
  fireEvent.click(await screen.findByRole("tab", { name: "Export" }, { timeout: 20_000 }));
  fireEvent.change(screen.getByLabelText("Label"), { target: { value: "E2E recruiter" } });
  fireEvent.click(screen.getByRole("button", { name: "Create link" }));
  const box = (await screen.findByLabelText("Share link", {}, { timeout: 10_000 })) as HTMLInputElement;
  const path = new URL(box.value).pathname;
  expect(path).toMatch(/^\/share\/[\w-]{20,}$/);
  view.unmount();

  view = renderAs(null, path); // recruiter: not signed in
  await screen.findByRole("heading", { name: /Kaveri Systems: Embedded Software Engineer/ }, { timeout: 20_000 });
  const rows = within(screen.getByRole("table", { name: "Shortlisted students" })).getAllByRole("row");
  expect(rows.length).toBeGreaterThan(1);
  expect(screen.queryByRole("columnheader", { name: "Name" })).toBeNull(); // blind by default
  view.unmount();

  // Revoke: the page now says the link is gone.
  const links = await api<{ id: number; label: string }[]>(`/tpo/drives/${kaveri.id}/share-links`, {}, tpo);
  await api(`/tpo/share-links/${links.find((l) => l.label === "E2E recruiter")!.id}`, { method: "DELETE" }, tpo);
  view = renderAs(null, path);
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/expired or was revoked/), { timeout: 10_000 });
  view.unmount();
}, 180_000);
