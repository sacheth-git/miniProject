/**
 * End-to-end drive lifecycle in the UI, against the real API:
 * TPO creates a drive -> student applies -> TPO shortlists, runs rounds, records an offer -> student accepts.
 * Run with the API on :8000:   $env:E2E="1"; npx vitest run src/test/e2e_campus.test.tsx
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterAll, beforeAll, expect, test, vi } from "vitest";
import { api, E2E, installFetch, renderAs, type Session } from "./e2eHarness";

const run = E2E ? test : test.skip;
const stamp = Date.now();
let tpo: Session;
let student: Session;

beforeAll(installFetch);
afterAll(async () => {
  if (student) await api("/auth/me", { method: "DELETE" }, student).catch(() => undefined);
  vi.restoreAllMocks();
});

const JD = `Responsibilities
- Build machine learning models in Python
Requirements
- Python, Machine Learning, SQL
Nice to have
- Docker`;

run("campus drive lifecycle in the UI: create -> apply -> shortlist -> rounds -> offer -> accept", async () => {
  // Accounts (API): a TPO with an institution, and a student who joins with consent and a resume.
  tpo = await api<Session>("/auth/register", { method: "POST", body: JSON.stringify({ email: `tpo-${stamp}@e2e.example`, password: "e2e-passw0rd", full_name: "E2E Officer", role: "tpo", institution_name: `E2E College ${stamp}` }) });
  const inst = await api<{ invite_code: string }>("/tpo/institution", {}, tpo);
  student = await api<Session>("/auth/register", { method: "POST", body: JSON.stringify({ email: `stu-${stamp}@e2e.example`, password: "e2e-passw0rd", full_name: "E2E Student", role: "job_seeker" }) });
  await api("/auth/join-institution", { method: "POST", body: JSON.stringify({ invite_code: inst.invite_code, consent: true, roll_no: "E2E001" }) }, student);
  const pdf = readFileSync(resolve(__dirname, "../../../backend/data/samples/uday_ml.pdf"));
  const fd = new FormData();
  fd.append("file", new Blob([pdf], { type: "application/pdf" }), "uday.pdf");
  const up = await fetch("http://127.0.0.1:8000/resume/upload", { method: "POST", body: fd, headers: { Authorization: `Bearer ${student.access_token}` } });
  expect(up.status).toBe(201);

  // 1. TPO creates and opens the drive through the wizard.
  let view = renderAs(tpo, "/tpo/drives/new");
  fireEvent.change(await screen.findByLabelText("Company"), { target: { value: "E2E Analytics" } });
  fireEvent.change(screen.getByLabelText("Role"), { target: { value: "ML Engineer" } });
  fireEvent.change(screen.getByLabelText("CTC (lakh per annum)"), { target: { value: "9" } });
  fireEvent.change(screen.getByLabelText(/Job description/), { target: { value: JD } });
  fireEvent.click(screen.getByRole("button", { name: "Extract skills" }));
  expect(await screen.findByLabelText("Python weight", {}, { timeout: 20_000 })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next" })); // -> eligibility
  fireEvent.click(screen.getByRole("button", { name: "Next" })); // -> rounds
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "open" } });
  fireEvent.click(screen.getByRole("button", { name: "Create drive" }));
  await screen.findByRole("heading", { name: "E2E Analytics: ML Engineer" }, { timeout: 20_000 });
  const drives = await api<{ id: string }[]>("/tpo/drives", {}, tpo);
  const driveId = drives[0].id;
  view.unmount();

  // 2. Student sees it (notified), opens it from Campus drives and applies.
  const notes = await api<{ items: { title: string }[] }>("/student/notifications", {}, student);
  expect(notes.items.some((n) => n.title === "New drive: E2E Analytics")).toBe(true);
  view = renderAs(student, "/campus");
  fireEvent.click(await screen.findByRole("link", { name: "ML Engineer" }, { timeout: 20_000 }));
  fireEvent.click(await screen.findByRole("button", { name: "Apply to this drive" }, { timeout: 20_000 }));
  await screen.findByRole("button", { name: "Withdraw application" }, { timeout: 20_000 });
  view.unmount();

  // 3. TPO shortlists, moves through both rounds on the Kanban, then records the offer.
  view = renderAs(tpo, `/tpo/drives/${driveId}`);
  const box = await screen.findByRole("checkbox", { name: "Shortlist E2E001" }, { timeout: 20_000 });
  fireEvent.click(box);
  await waitFor(() => expect(screen.getByRole("checkbox", { name: "Shortlist E2E001" })).toBeChecked(), { timeout: 20_000 });

  fireEvent.click(screen.getByRole("tab", { name: "Rounds" }));
  for (const stage of ["Online test", "Technical interview", "HR interview"]) {
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select E2E001" }, { timeout: 10_000 }));
    fireEvent.change(screen.getByLabelText(/Move 1 selected to/), { target: { value: stage } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    const col = await screen.findByRole("region", { name: `${stage} (1)` }, { timeout: 10_000 });
    expect(within(col).getByText("E2E001")).toBeInTheDocument();
  }

  fireEvent.click(screen.getByRole("tab", { name: "Offers" }));
  const pick = await screen.findByLabelText("Record an offer for");
  await waitFor(() => expect(within(pick).getAllByRole("option").length).toBeGreaterThan(1));
  fireEvent.change(pick, { target: { value: within(pick).getAllByRole("option")[1].getAttribute("value") } });
  fireEvent.click(screen.getByRole("button", { name: "Record offer" }));
  await screen.findByText("9 LPA", {}, { timeout: 10_000 });
  view.unmount();

  // 4. Student accepts the offer.
  view = renderAs(student, `/campus/${driveId}`);
  fireEvent.click(await screen.findByRole("button", { name: "Accept offer" }, { timeout: 20_000 }));
  await screen.findByText("Offer accepted", {}, { timeout: 20_000 });
  const step = screen.getByText("Accepted", { selector: "[aria-current='step']" });
  expect(step).toBeInTheDocument();
  view.unmount();

  const detail = await api<{ stage: string; timeline: { stage: string }[] }>(`/student/drives/${driveId}`, {}, student);
  expect(detail.stage).toBe("Accepted");
  expect(detail.timeline.map((t) => t.stage)).toEqual(["Applied", "Shortlisted", "Online test", "Technical interview", "HR interview", "Offer", "Accepted"]);
  const roster = await api<{ roll_no: string; placed_status: string }[]>("/tpo/students", {}, tpo);
  expect(roster.find((r) => r.roll_no === "E2E001")?.placed_status).toBe("placed");
  console.log("lifecycle timeline:", detail.timeline.map((t) => t.stage).join(" -> "));
}, 180_000);
