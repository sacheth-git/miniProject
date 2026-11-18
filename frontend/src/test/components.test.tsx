import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApplyMenu, applyLabel } from "../components/ApplyMenu";
import { FilterBar } from "../components/FilterBar";
import { JobCard } from "../components/JobCard";
import { MatchRing } from "../components/ui";
import { experienceLabel, timeAgo } from "../lib/format";
import { job, matchItem, renderApp } from "./helpers";

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("[]", { status: 200 }));
  localStorage.clear();
});
afterEach(() => vi.restoreAllMocks());

describe("ApplyMenu", () => {
  test("Apply opens the employer's page in one click; the chevron lists every option", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    renderApp(<ApplyMenu job={job()} />);
    fireEvent.click(screen.getByRole("button", { name: /^apply$/i }));
    expect(open).toHaveBeenCalledWith("https://boards.greenhouse.io/nimbus/jobs/1", "_blank", "noopener,noreferrer");
    fireEvent.click(screen.getByRole("button", { name: "More ways to apply" }));
    const items = screen.getAllByRole("menuitem").map((m) => m.textContent);
    expect(items).toEqual(["Job page on company site", "Apply on LinkedIn", "Apply on Naukri"]);
    fireEvent.click(screen.getByRole("menuitem", { name: /naukri/i }));
    expect(open).toHaveBeenCalledWith("https://www.naukri.com/job-listings-1", "_blank", "noopener,noreferrer");
  });

  test("a single option is one Apply button with no menu", () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const single = job({ apply_options: [{ publisher: "Acme careers (Lever)", url: "https://jobs.lever.co/acme/1/apply", is_direct: true }] });
    renderApp(<ApplyMenu job={single} />);
    expect(screen.queryByRole("button", { name: "More ways to apply" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^apply$/i }));
    expect(open).toHaveBeenCalledWith("https://jobs.lever.co/acme/1/apply", "_blank", "noopener,noreferrer");
  });

  test("labels", () => {
    expect(applyLabel({ publisher: "Stripe careers (Greenhouse)", url: "", is_direct: true })).toBe("company site");
    expect(applyLabel({ publisher: "LinkedIn", url: "", is_direct: false })).toBe("LinkedIn");
    expect(applyLabel({ publisher: "Stripe application form", url: "", is_direct: true })).toBe("application form");
  });
});

test("JobCard shows match ring, matched skills in green and missing required in red", () => {
  const onSelect = vi.fn();
  renderApp(<JobCard job={job()} match={matchItem()} selected={false} onSelect={onSelect} />);
  expect(screen.getByRole("img", { name: "82% match" })).toBeInTheDocument();
  expect(screen.getByText("PyTorch").className).toMatch(/emerald/);
  expect(screen.getByText("Kubernetes").className).toMatch(/rose/);
  expect(screen.getByText("via LinkedIn")).toBeInTheDocument();
  expect(screen.getByText("3 days ago")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Machine Learning Engineer" }));
  expect(onSelect).toHaveBeenCalled();
});

test("FilterBar submits role and location and maps experience bands", () => {
  const onChange = vi.fn();
  renderApp(<FilterBar value={{}} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Role or keyword"), { target: { value: "data analyst" } });
  fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Pune" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  expect(onChange).toHaveBeenLastCalledWith({ role: "data analyst", location: "Pune" });
  fireEvent.change(screen.getByLabelText("Experience"), { target: { value: "1-3" } });
  expect(onChange).toHaveBeenLastCalledWith({ min_exp: "1", max_exp: "3" });
});

test("MatchRing clamps and format helpers", () => {
  renderApp(<MatchRing percent={140} />);
  expect(screen.getByRole("img", { name: "100% match" })).toBeInTheDocument();
  expect(experienceLabel(0, null)).toBe("Entry level");
  expect(experienceLabel(2, 5)).toBe("2-5 yrs");
  expect(experienceLabel(null, null)).toBeNull();
  expect(timeAgo(null)).toBe("Date not listed");
  expect(timeAgo(new Date().toISOString())).toBe("Today");
});
