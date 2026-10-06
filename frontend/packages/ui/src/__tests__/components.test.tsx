import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "../components/button";
import { ConfirmDialog } from "../components/dialog";
import { Field } from "../components/field";
import { Input } from "../components/input";
import { Meter } from "../components/stat";
import { formatRelative, pluralize } from "../lib/format";
import { applyBrandTokens } from "../theme";

describe("Field", () => {
  it("wires label, description and error to the control for screen readers", () => {
    render(
      <Field label="Email" description="We'll send results here" error="Enter a valid email" required>
        <Input />
      </Field>,
    );
    const input = screen.getByLabelText(/Email/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-required", "true");
    const describedBy = input.getAttribute("aria-describedby") ?? "";
    expect(document.getElementById(describedBy.split(" ").pop() ?? "")).toHaveTextContent(
      "Enter a valid email",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email");
  });
});

describe("Button", () => {
  it("is disabled and announces busy state while loading", () => {
    render(<Button loading>Save</Button>);
    const button = screen.getByRole("button", { name: /Save/ });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});

function ConfirmHarness({ onConfirm }: { onConfirm: (reason: string) => void }) {
  const [open, setOpen] = useState(true);
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={setOpen}
      title="Withdraw publication?"
      confirmLabel="Withdraw"
      variant="danger"
      requireReason
      onConfirm={onConfirm}
    />
  );
}

describe("ConfirmDialog", () => {
  it("requires a reason before confirming and passes it to the handler", async () => {
    const onConfirm = vi.fn();
    render(<ConfirmHarness onConfirm={onConfirm} />);
    const confirm = screen.getByRole("button", { name: "Withdraw" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Reason/), "Wrong marks for CSE-G3");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith("Wrong marks for CSE-G3");
  });
});

describe("Meter", () => {
  it("exposes usage to assistive tech and shows unlimited plans", () => {
    const { rerender } = render(<Meter label="Students" value={140} max={150} />);
    expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow", "140");
    expect(screen.getByText(/of 150/)).toBeInTheDocument();
    rerender(<Meter label="Students" value={140} max={null} />);
    expect(screen.getByText(/Unlimited/)).toBeInTheDocument();
  });
});

describe("applyBrandTokens", () => {
  it("applies valid colours and ignores anything that isn't a hex colour", () => {
    const root = document.createElement("div");
    applyBrandTokens(
      {
        primary: "#8c1d18",
        primary_contrast: "#ffffff",
        primary_ink: "red; background:url(x)",
        accent: "#1f4e79",
        font_family: "Comic Sans",
      },
      root,
    );
    expect(root.style.getPropertyValue("--sc-brand")).toBe("#8c1d18");
    expect(root.style.getPropertyValue("--sc-brand-ink-light")).toBe("");
    expect(root.style.getPropertyValue("--sc-font-family")).toBe("");
  });
});

describe("format helpers", () => {
  it("formats relative times and plurals", () => {
    const now = new Date("2026-10-06T12:00:00Z");
    expect(formatRelative("2026-10-06T11:59:50Z", now)).toBe("just now");
    expect(formatRelative("2026-10-06T10:00:00Z", now)).toBe("2 hours ago");
    expect(formatRelative(null, now)).toBe("Never");
    expect(pluralize(1, "student")).toBe("1 student");
    expect(pluralize(1200, "student")).toBe("1,200 students");
  });
});
