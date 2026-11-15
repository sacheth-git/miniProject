import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import { DataTable, type Column } from "../components/DataTable";

interface Row { id: string; name: string; cgpa: number | null }
const rows: Row[] = Array.from({ length: 30 }, (_, i) => ({ id: `r${i}`, name: `Student ${String(i).padStart(2, "0")}`, cgpa: i === 5 ? null : 5 + (i % 10) / 2 }));
const cols: Column<Row>[] = [{ key: "name", header: "Name" }, { key: "cgpa", header: "CGPA", align: "right" }];

const bodyNames = () => within(screen.getAllByRole("rowgroup")[1]).getAllByRole("row").map((r) => r.firstChild?.textContent);

test("sorts by clicking headers (aria-sort), keeps blanks last, and paginates", () => {
  render(<DataTable caption="Students" rows={rows} columns={cols} rowKey={(r) => r.id} pageSize={10} />);
  expect(bodyNames()).toHaveLength(10);
  expect(screen.getByText("1-10 of 30")).toBeInTheDocument();

  const cgpaBtn = screen.getByRole("button", { name: /CGPA/ });
  fireEvent.click(cgpaBtn);
  expect(cgpaBtn.closest("th")).toHaveAttribute("aria-sort", "ascending");
  fireEvent.click(cgpaBtn);
  expect(cgpaBtn.closest("th")).toHaveAttribute("aria-sort", "descending");
  const top = within(screen.getAllByRole("rowgroup")[1]).getAllByRole("row")[0];
  expect(top.lastChild?.textContent).toBe("9.5");

  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  const last = within(screen.getAllByRole("rowgroup")[1]).getAllByRole("row").at(-1)!;
  expect(last.firstChild?.textContent).toBe("Student 05"); // the blank CGPA sorts last
});

test("filters rows", () => {
  render(<DataTable caption="Students" rows={rows} columns={cols} rowKey={(r) => r.id} filter="student 1" filterText={(r) => r.name} />);
  expect(bodyNames()).toEqual(["Student 10", "Student 11", "Student 12", "Student 13", "Student 14", "Student 15", "Student 16", "Student 17", "Student 18", "Student 19"]);
});
