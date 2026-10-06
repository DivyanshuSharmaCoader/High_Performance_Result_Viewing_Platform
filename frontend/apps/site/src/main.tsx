import "./index.css";

import { createQueryClient } from "@scorecode/api-client";
import { Toaster, applyBrandTokens, applyColorScheme, buttonClasses } from "@scorecode/ui";
import { QueryClientProvider } from "@tanstack/react-query";
import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { Link, Outlet, RouterProvider, createBrowserRouter } from "react-router";

import HomePage from "./features/home";

const Signup = lazy(() => import("./features/signup"));
const Verify = lazy(() => import("./features/verify"));

applyColorScheme("light");
applyBrandTokens({
  primary: "#3730a3",
  primary_contrast: "#ffffff",
  primary_ink: "#3730a3",
  accent: "#0f766e",
  font_family: "Inter",
});

function Layout() {
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <Link to="/" className="flex items-center gap-2.5" aria-label="ScoreCode home">
            <span className="flex size-8 items-center justify-center rounded-lg bg-[#1e1b4b] text-xs font-bold text-white">
              SC
            </span>
            <span className="text-[15px] font-semibold tracking-[-0.01em]">ScoreCode</span>
          </Link>
          <nav aria-label="Main" className="flex items-center gap-1 sm:gap-2">
            <a
              href="/#how-it-works"
              className="hidden rounded-md px-3 py-2 text-sm text-fg-muted hover:text-fg sm:block"
            >
              How it works
            </a>
            <a
              href="/#plans"
              className="hidden rounded-md px-3 py-2 text-sm text-fg-muted hover:text-fg sm:block"
            >
              Plans
            </a>
            <Link to="/signup" className={buttonClasses("primary", "md")}>
              Start free
            </Link>
          </nav>
        </div>
      </header>
      <main className="flex-1">
        <Suspense fallback={<div className="h-96" aria-busy="true" />}>
          <Outlet />
        </Suspense>
      </main>
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 py-8 text-[13px] text-fg-subtle sm:flex-row sm:justify-between">
          <span>© {new Date().getFullYear()} ScoreCode</span>
          <span>Results infrastructure for educational institutions in India</span>
        </div>
      </footer>
    </div>
  );
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "/signup", element: <Signup /> },
      { path: "/signup/verify", element: <Verify /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>
  </StrictMode>,
);
