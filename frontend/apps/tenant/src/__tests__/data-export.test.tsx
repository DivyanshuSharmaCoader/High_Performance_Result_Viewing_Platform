import type { DataExport } from "@scorecode/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReauthProvider } from "../components/reauth";
import { CloseAccountSection, DataExportPage } from "../features/admin/data";
import { meKey } from "../lib/session";
import { TenantProvider, tenantConfigKey } from "../lib/tenant";
import { mockApi, ownerMe, renderRoutes, tenantConfig } from "./test-utils";

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

describe("closing the account (P18.14)", () => {
  function section() {
    return renderRoutes(
      [
        {
          path: "/s",
          element: (
            <TenantProvider>
              <ReauthProvider>
                <CloseAccountSection />
              </ReauthProvider>
            </TenantProvider>
          ),
        },
      ],
      "/s",
      (qc) => {
        qc.setQueryData(meKey, { ...ownerMe, permissions: [...ownerMe.permissions, "account.close"] });
        qc.setQueryData(tenantConfigKey, tenantConfig);
      },
    );
  }

  it("asks for the address typed out, then shows the date and a way back", async () => {
    document.cookie = "sc_csrf=test-token";
    let requested = false;
    const sent: unknown[] = [];
    mockApi({
      "GET /api/v1/admin/closure": () => ({
        status: 200,
        body: requested
          ? {
              requested: true,
              requested_at: "2026-10-10T08:00:00Z",
              delete_after: "2026-11-09T08:00:00Z",
              reason: "x",
            }
          : { requested: false, requested_at: null, delete_after: null, reason: null },
      }),
      "POST /api/v1/admin/closure": (_u, init) => {
        sent.push(JSON.parse(String(init.body)));
        requested = true;
        return { status: 201, body: {} };
      },
    });
    section();
    await userEvent.click(await screen.findByRole("button", { name: "Close the account…" }));
    const dialog = screen.getByRole("dialog", { name: "Close your ScoreCode account?" });
    const confirm = within(dialog).getByRole("button", { name: "Close the account" });
    await userEvent.type(within(dialog).getByLabelText(/Why are you leaving/), "Moving to another system");
    expect(confirm).toBeDisabled(); // the address isn't typed yet
    await userEvent.type(within(dialog).getByRole("textbox", { name: /demo/ }), "demo");
    await userEvent.click(confirm);
    await waitFor(() => expect(sent).toEqual([{ reason: "Moving to another system", confirm: "demo" }]));
    expect(await screen.findByText(/Your data will be erased after/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel closure" })).toBeInTheDocument();
  });
});
