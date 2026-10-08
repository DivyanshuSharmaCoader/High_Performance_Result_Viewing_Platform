import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Outlet } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReauthProvider } from "../components/reauth";
import { TwoStepSection } from "../features/account/two-step";
import LoginPage from "../features/auth/login";
import { meKey } from "../lib/session";
import { TenantProvider } from "../lib/tenant";
import { mockApi, ownerMe, renderRoutes, tenantConfig } from "./test-utils";

afterEach(() => vi.restoreAllMocks());

describe("two-step sign-in", () => {
  it("asks for the authenticator code after a right password, keeping what was typed", async () => {
    document.cookie = "sc_csrf=t0ken";
    const bodies: Record<string, string>[] = [];
    mockApi({
      "GET /api/v1/tenant/config": () => ({ status: 200, body: tenantConfig }),
      "POST /api/v1/auth/login": (_u, init) => {
        const body = JSON.parse(String(init.body));
        bodies.push(body);
        if (!body.totp_code)
          return {
            status: 401,
            body: { code: "totp-required", detail: "Enter the code from your authenticator app" },
          };
        if (body.totp_code === "111111")
          return { status: 401, body: { code: "invalid-credentials", detail: "x" } };
        return { status: 200, body: { user_kind: "staff", roles: ["institution_owner"] } };
      },
      "GET /api/v1/me": () => ({ status: 200, body: ownerMe }),
    });
    renderRoutes(
      [
        {
          element: (
            <TenantProvider>
              <Outlet />
            </TenantProvider>
          ),
          children: [
            { path: "/login", element: <LoginPage /> },
            { path: "/admin", element: <p>Admin home</p> },
          ],
        },
      ],
      "/login",
    );
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email or enrollment number"), "principal@demo.example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Two-step sign-in" })).toBeInTheDocument();
    const code = screen.getByLabelText("Authenticator code");
    expect(code).toHaveAttribute("autocomplete", "one-time-code");
    await user.type(code, "111111");
    await user.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByText(/That code didn't match/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Use a recovery code" }));
    await user.type(screen.getByLabelText("Recovery code"), "ABCDE-FGHJK");
    await user.click(screen.getByRole("button", { name: "Verify and sign in" }));
    expect(await screen.findByText("Admin home")).toBeInTheDocument();
    expect(bodies.at(-1)).toEqual({
      login_id: "principal@demo.example.com",
      password: "correct-horse-battery",
      totp_code: "ABCDE-FGHJK",
    });
  });

  it("sets up with a QR code, then shows recovery codes that must be saved", async () => {
    document.cookie = "sc_csrf=t0ken";
    let enabled = false;
    const codes = Array.from({ length: 10 }, (_, i) => `AAAA${i}-BBBB${i}`);
    mockApi({
      "GET /api/v1/me/mfa": () => ({
        status: 200,
        body: {
          enabled,
          enabled_at: enabled ? "2026-10-08T06:00:00Z" : null,
          recovery_codes_left: enabled ? 10 : 0,
        },
      }),
      "GET /api/v1/me": () => ({ status: 200, body: { ...ownerMe, mfa_enabled: enabled } }),
      "POST /api/v1/me/mfa/setup": () => ({
        status: 200,
        body: {
          secret: "JBSWY3DPEHPK3PXP",
          uri: "otpauth://totp/x",
          qr_svg: "data:image/svg+xml;base64,PHN2Zy8+",
        },
      }),
      "POST /api/v1/me/mfa/enable": (_u, init) => {
        if (JSON.parse(String(init.body)).code !== "123456")
          return { status: 422, body: { code: "validation-failed", detail: "That code didn't match." } };
        enabled = true;
        return { status: 200, body: { recovery_codes: codes } };
      },
    });
    renderRoutes(
      [
        {
          path: "/account",
          element: (
            <ReauthProvider>
              <TwoStepSection />
            </ReauthProvider>
          ),
        },
      ],
      "/account",
      (qc) => qc.setQueryData(meKey, ownerMe),
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Set up two-step sign-in" }));
    const dialog = await screen.findByRole("dialog", { name: "Set up two-step sign-in" });
    expect(within(dialog).getByRole("img", { name: /QR code/ })).toHaveAttribute(
      "src",
      expect.stringMatching(/^data:image\/svg/),
    );
    expect(within(dialog).getByText("JBSW Y3DP EHPK 3PXP")).toBeInTheDocument();
    const input = within(dialog).getByLabelText("Code from the app");
    await user.type(input, "12a3456"); // letters are dropped
    expect(input).toHaveValue("123456");
    await user.click(within(dialog).getByRole("button", { name: "Turn on" }));

    const saved = await screen.findByRole("dialog", { name: "Two-step sign-in is on" });
    expect(within(saved).getAllByRole("listitem")).toHaveLength(10);
    const done = within(saved).getByRole("button", { name: "Done" });
    expect(done).toBeDisabled();
    await user.click(within(saved).getByRole("checkbox", { name: "I've saved my recovery codes" }));
    await user.click(done);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(await screen.findByText(/10 recovery codes left/)).toBeInTheDocument();
  });
});
