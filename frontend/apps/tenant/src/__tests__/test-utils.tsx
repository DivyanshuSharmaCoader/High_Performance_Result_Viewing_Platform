import type { Me, TenantConfig } from "@scorecode/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { RouterProvider, createMemoryRouter, type RouteObject } from "react-router";
import { vi } from "vitest";

export const tenantConfig: TenantConfig = {
  tenant: { slug: "demo", name: "Demo Public School" },
  branding: {
    display_name: "Demo Public School",
    short_name: null,
    logo_url: null,
    logo_version: 1,
    login_heading: null,
    login_message: null,
    footer_text: null,
    support_email: null,
    show_powered_by: true,
    tokens: {
      primary: "#2952cc",
      primary_contrast: "#ffffff",
      primary_ink: "#2952cc",
      accent: "#0f766e",
      accent_contrast: "#ffffff",
      font_family: "Inter",
    },
  },
  settings: { student_activation_mode: "code", locale: "en-IN" },
  features: {},
};

export const ownerMe: Me = {
  id: "u1",
  full_name: "Priya Malhotra",
  email: "principal@demo.example.com",
  login_id: "principal@demo.example.com",
  kind: "staff",
  roles: ["institution_owner"],
  permissions: [
    "students.view",
    "staff.view",
    "staff.manage",
    "settings.manage",
    "subscription.view",
    "audit.view",
  ],
  tenant: { id: "t1", slug: "demo", name: "Demo Public School" },
  features: {},
  plan: { code: "free", name: "Free", status: "active", period_end: null },
  reauthenticated_at: null,
};

type Handler = (url: string, init: RequestInit) => { status: number; body?: unknown };

/** Route fetch calls by path; unmatched requests fail the test loudly. */
export function mockApi(handlers: Record<string, Handler>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    const path = url.split("?")[0] ?? url;
    const key = `${init?.method ?? "GET"} ${path}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`Unexpected request ${key}`);
    const { status, body } = handler(url, init ?? {});
    return new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": status >= 400 ? "application/problem+json" : "application/json" },
    });
  });
}

export function renderRoutes(routes: RouteObject[], initialPath: string): ReturnType<typeof render> {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] });
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}
