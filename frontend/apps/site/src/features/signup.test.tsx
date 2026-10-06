import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import SignupPage from "./signup";

afterEach(() => vi.restoreAllMocks());

function renderSignup() {
  const router = createMemoryRouter([{ path: "/signup", element: <SignupPage /> }], {
    initialEntries: ["/signup"],
  });
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("sign-up", () => {
  it("suggests a portal address from the institution name and shows availability", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ available: true, reason: null }), { status: 200 }),
    );
    renderSignup();
    await userEvent.type(screen.getByLabelText("Institution name"), "St. Mary's Convent School");
    expect(screen.getByLabelText("Portal address")).toHaveValue("smcs");
    expect(await screen.findByText("Available", {}, { timeout: 2000 })).toBeInTheDocument();
    // Debounced: typing a whole name triggers one availability request, not one per keystroke.
    expect((globalThis.fetch as unknown as { mock: { calls: unknown[] } }).mock.calls.length).toBe(1);
  });

  it("shows server-side field errors next to the field", async () => {
    document.cookie = "sc_csrf=x";
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("slug-availability"))
        return new Response(JSON.stringify({ available: true, reason: null }));
      return new Response(
        JSON.stringify({
          code: "validation-failed",
          detail: "Please use your institution or personal email address.",
          field: "email",
        }),
        {
          status: 422,
        },
      );
    });
    renderSignup();
    await userEvent.type(screen.getByLabelText("Institution name"), "Sunrise Coaching");
    await userEvent.type(screen.getByLabelText("Your name"), "Anita Desai");
    await userEvent.type(screen.getByLabelText("Work email"), "anita@mailinator.com");
    await userEvent.type(screen.getByLabelText("Password"), "a-long-passphrase-here");
    await userEvent.click(screen.getByRole("button", { name: "Create portal" }));
    expect(
      await screen.findByText("Please use your institution or personal email address."),
    ).toBeInTheDocument();
  });
});
