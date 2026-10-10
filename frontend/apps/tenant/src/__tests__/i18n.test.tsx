import type { Me, MyResultItem } from "@scorecode/api-client";
import { writeUiPref } from "@scorecode/ui";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StudentShell } from "../components/student-shell";
import StudentHome from "../features/student/home";
import en from "../lib/i18n/en";
import hi from "../lib/i18n/hi";
import pa from "../lib/i18n/pa";
import { langOf } from "../lib/i18n";
import { meKey } from "../lib/session";
import { TenantProvider, tenantConfigKey } from "../lib/tenant";
import { mockApi, ownerMe, renderRoutes, tenantConfig } from "./test-utils";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  document.documentElement.lang = "en";
});

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("catalogues (decision D29)", () => {
  it("translate every English message with the same placeholders", () => {
    for (const [name, cat] of [
      ["hi", hi],
      ["pa", pa],
    ] as const) {
      for (const [key, text] of Object.entries(en)) {
        const translated = cat[key as keyof typeof en];
        expect(translated?.trim(), `${name} ${key}`).toBeTruthy();
        expect(placeholders(translated), `${name} ${key}`).toEqual(placeholders(text));
      }
    }
  });

  it("reads institution locales", () => {
    expect(["hi-IN", "pa-IN", "en-IN", "ta-IN", null].map(langOf)).toEqual(["hi", "pa", "en", "en", "en"]);
  });
});

const student: Me = {
  ...ownerMe,
  full_name: "Aarav Gupta",
  login_id: "102401001",
  email: null,
  kind: "student",
  roles: ["student"],
  permissions: ["me.results"],
};
const latest: MyResultItem = {
  publication_id: "p1",
  published_at: "2026-10-07T10:00:00Z",
  revised: false,
  exam: { name: "Half-yearly", kind: "term", term: "Term 1", session: "2025-26" },
  outcome: "pass",
  percentage: "85",
  grade: "A2",
  sgpa: null,
};

function home(locale: string) {
  mockApi({ "GET /api/v1/me/results": () => ({ status: 200, body: [latest] }) });
  return renderRoutes(
    [
      {
        path: "/me",
        element: (
          <TenantProvider>
            <StudentShell>
              <StudentHome />
            </StudentShell>
          </TenantProvider>
        ),
      },
    ],
    "/me",
    (qc) => {
      qc.setQueryData(meKey, student);
      qc.setQueryData(tenantConfigKey, { ...tenantConfig, settings: { ...tenantConfig.settings, locale } });
    },
  );
}

describe("student portal languages", () => {
  it("opens in the institution's language and switches on this device", async () => {
    home("hi-IN");
    const card = await screen.findByRole("link", { name: /नवीनतम परिणाम/ });
    expect(card).toHaveTextContent("उत्तीर्ण");
    expect(card).toHaveTextContent("85%");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("नमस्ते, Aarav");
    await waitFor(() => expect(document.documentElement.lang).toBe("hi"));

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "भाषा" }), "pa");
    expect(await screen.findByRole("link", { name: /ਨਵਾਂ ਨਤੀਜਾ/ })).toHaveTextContent("ਪਾਸ");
    expect(localStorage.getItem("sc.lang")).toBe("pa");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "ਭਾਸ਼ਾ" }), "en");
    expect(await screen.findByRole("link", { name: /Latest result/ })).toHaveTextContent("Passed");
  });

  it("is English by default, and a device's own choice wins over the institution's", async () => {
    writeUiPref("lang", "en");
    home("pa-IN");
    expect(await screen.findByRole("link", { name: /Latest result/ })).toHaveTextContent("Passed");
  });
});
