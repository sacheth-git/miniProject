import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { RegisterPage } from "../pages/AuthPages";
import { renderApp } from "./helpers";

let bodies: Record<string, unknown>[] = [];

beforeEach(() => {
  bodies = [];
  localStorage.clear();
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/auth/register")) {
      bodies.push(JSON.parse(String(init?.body)));
      return new Response(JSON.stringify({ detail: "stop here" }), { status: 400, headers: { "Content-Type": "application/json" } });
    }
    return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  });
});
afterEach(() => vi.restoreAllMocks());

function fillBasics() {
  fireEvent.click(screen.getByRole("button", { name: /yes, i'm a student/i }));
  fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Asha Rao" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "asha@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "passw0rd123" } });
}

test("a student can sign up without an invite code; no consent box, account starts as a job seeker", async () => {
  renderApp(<RegisterPage />, "/register");
  fillBasics();
  expect(screen.getByLabelText(/invite code.*optional/i)).not.toBeRequired();
  expect(screen.queryByRole("checkbox")).toBeNull();
  const submit = screen.getByRole("button", { name: /create account/i });
  expect(submit).toBeEnabled();
  fireEvent.click(submit);
  await waitFor(() => expect(bodies).toHaveLength(1));
  expect(bodies[0]).toMatchObject({ role: "job_seeker", email: "asha@example.com" });
  expect(bodies[0].invite_code).toBeUndefined();
});

test("with an invite code the consent box appears and is required before joining as a student", async () => {
  renderApp(<RegisterPage />, "/register");
  fillBasics();
  fireEvent.change(screen.getByLabelText(/invite code/i), { target: { value: "witdemo1" } });
  const submit = screen.getByRole("button", { name: /create account/i });
  expect(submit).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  expect(submit).toBeEnabled();
  fireEvent.click(submit);
  await waitFor(() => expect(bodies).toHaveLength(1));
  expect(bodies[0]).toMatchObject({ role: "student", invite_code: "witdemo1", consent: true });
});
