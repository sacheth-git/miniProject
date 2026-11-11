import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";
import { StatusPage } from "../pages/StatusPage";

afterEach(() => vi.restoreAllMocks());

test("shows API status from /health", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({ status: "ok", version: "0.1.0", database: "ok", sources_configured: { adzuna: false } }),
      { status: 200 },
    ),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <StatusPage />
    </QueryClientProvider>,
  );
  expect(await screen.findByTestId("api-status")).toHaveTextContent("ok");
  expect(screen.getByText("no key (skipped)")).toBeInTheDocument();
});
