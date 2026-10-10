import type { DataExport } from "@scorecode/api-client";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReauthProvider } from "../components/reauth";
import { DataExportPage } from "../features/admin/data";
import { meKey } from "../lib/session";
import { mockApi, ownerMe, renderRoutes } from "./test-utils";

vi.mock("../lib/navigate", () => ({ goTo: vi.fn() }));
import { goTo } from "../lib/navigate";

afterEach(() => vi.restoreAllMocks());

const ready: DataExport = {
  id: "x1",
  status: "ready",
  created_at: "2026-10-10T08:00:00Z",
  finished_at: "2026-10-10T08:01:00Z",
  expires_at: "2026-10-17T08:01:00Z",
  size_bytes: 52_000,
  counts: { "students.csv": 120, "marks.csv": 900 },
};

function page(permissions: string[]) {
  return renderRoutes(
    [
      {
        path: "/admin/settings/data",
        element: (
          <ReauthProvider>
            <DataExportPage />
          </ReauthProvider>
        ),
      },
    ],
    "/admin/settings/data",
    (qc) => qc.setQueryData(meKey, { ...ownerMe, permissions }),
  );
}

describe("data export (P18.5)", () => {
  it("lets the owner request an export and download a ready one", async () => {
    document.cookie = "sc_csrf=test-token";
    const calls: string[] = [];
    mockApi({
      "GET /api/v1/admin/exports": () => ({ status: 200, body: [ready] }),
      "POST /api/v1/admin/exports": () => {
        calls.push("request");
        return { status: 202, body: { ...ready, id: "x2", status: "queued" } };
      },
      "POST /api/v1/admin/exports/x1/link": () => ({
        status: 200,
        body: { url: "https://files.example/x1.zip?sig=1", filename: "scorecode-export-2026-10-10.zip" },
      }),
    });
    page([...ownerMe.permissions, "data.export"]);
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByText(/1,020 rows/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Download" }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith("https://files.example/x1.zip?sig=1"));
    await userEvent.click(screen.getByRole("button", { name: "Export everything" }));
    await waitFor(() => expect(calls).toEqual(["request"]));
  });

  it("tells administrators who aren't the owner to ask the owner", () => {
    page(ownerMe.permissions);
    expect(screen.getByText(/Only the institution's owner can export/)).toBeInTheDocument();
  });
});
