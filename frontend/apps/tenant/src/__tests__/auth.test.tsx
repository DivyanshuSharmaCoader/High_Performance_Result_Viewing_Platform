import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Outlet } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import LoginPage from "../features/auth/login";
import { RequireAuth, safeNext } from "../lib/session";
import { TenantProvider } from "../lib/tenant";
import { mockApi, ownerMe, renderRoutes, tenantConfig } from "./test-utils";

afterEach(() => vi.restoreAllMocks());

function withTenant() {
  return (
    <TenantProvider>
      <Outlet />
    </TenantProvider>
  );
}

describe("login page", () => {
  it("validates required fields before calling the API", async () => {
    const fetchMock = mockApi({ "GET /api/v1/tenant/config": () => ({ status: 200, body: tenantConfig }) });
    renderRoutes(
      [{ element: withTenant(), children: [{ path: "/login", element: <LoginPage /> }] }],
      "/login",
    );
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email or enrollment number")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1); // only the tenant config
  });

  it("shows the server's generic error and clears the password on bad credentials", async () => {
    document.cookie = "sc_csrf=t0ken";
    mockApi({
      "GET /api/v1/tenant/config": () => ({ status: 200, body: tenantConfig }),
      "POST /api/v1/auth/login": () => ({
        status: 401,
        body: { code: "invalid-credentials", detail: "Check your login details." },
      }),
    });
    renderRoutes(
      [{ element: withTenant(), children: [{ path: "/login", element: <LoginPage /> }] }],
      "/login",
    );
    await userEvent.type(
      await screen.findByLabelText("Email or enrollment number"),
      "principal@demo.example.com",
    );
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Check your login details.")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveValue("");
  });

  it("signs in and lands on the role's home page", async () => {
    document.cookie = "sc_csrf=t0ken";
    mockApi({
      "GET /api/v1/tenant/config": () => ({ status: 200, body: tenantConfig }),
      "POST /api/v1/auth/login": () => ({
        status: 200,
        body: { user_kind: "staff", roles: ["institution_owner"] },
      }),
      "GET /api/v1/me": () => ({ status: 200, body: ownerMe }),
    });
    renderRoutes(
      [
        {
          element: withTenant(),
          children: [
            { path: "/login", element: <LoginPage /> },
            { path: "/admin", element: <p>Admin home</p> },
          ],
        },
      ],
      "/login",
    );
    await userEvent.type(
      await screen.findByLabelText("Email or enrollment number"),
      "principal@demo.example.com",
    );
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Admin home")).toBeInTheDocument();
  });
});

describe("route guard", () => {
  it("sends anonymous visitors to the login page with a safe return path", async () => {
    mockApi({
      "GET /api/v1/tenant/config": () => ({ status: 200, body: tenantConfig }),
      "GET /api/v1/me": () => ({
        status: 401,
        body: { code: "not-authenticated", detail: "Please sign in" },
      }),
    });
    renderRoutes(
      [
        {
          element: withTenant(),
          children: [
            { element: <RequireAuth />, children: [{ path: "/admin/staff", element: <p>Staff</p> }] },
            { path: "/login", element: <p>Login page</p> },
          ],
        },
      ],
      "/admin/staff",
    );
    expect(await screen.findByText("Login page")).toBeInTheDocument();
  });

  it("rejects open redirects in ?next=", () => {
    expect(safeNext("/admin/staff")).toBe("/admin/staff");
    expect(safeNext("//evil.example.com")).toBeNull();
    expect(safeNext("https://evil.example.com")).toBeNull();
    expect(safeNext("/\\evil.example.com")).toBeNull();
    expect(safeNext(null)).toBeNull();
  });
});

describe("tenant bootstrap", () => {
  it("shows the unavailable page for suspended institutions", async () => {
    mockApi({
      "GET /api/v1/tenant/config": () => ({
        status: 403,
        body: { code: "tenant-unavailable", detail: "Unavailable", institution: "Demo Public School" },
      }),
    });
    renderRoutes([{ path: "/", element: withTenant() }], "/");
    expect(await screen.findByText("Portal temporarily unavailable")).toBeInTheDocument();
    expect(screen.getByText("Demo Public School")).toBeInTheDocument();
  });

  it("explains unknown addresses", async () => {
    mockApi({
      "GET /api/v1/tenant/config": () => ({ status: 404, body: { code: "not-found", detail: "No" } }),
    });
    renderRoutes([{ path: "/", element: withTenant() }], "/");
    await waitFor(() => expect(screen.getByText("There's no institution here")).toBeInTheDocument());
  });
});
