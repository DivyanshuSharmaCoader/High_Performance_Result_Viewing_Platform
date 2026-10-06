import { lazy, Suspense, type ComponentType } from "react";
import { Outlet, createBrowserRouter, useRouteError } from "react-router";

import { Shell } from "./components/shell";
import { RequireAuth } from "./lib/session";

const page = (load: () => Promise<{ default: ComponentType }>) => lazy(load);
const Login = page(() => import("./features/login"));
const Overview = page(() => import("./features/overview"));
const Tenants = page(() => import("./features/tenants"));
const TenantDetail = page(() => import("./features/tenant-detail"));
const Plans = page(() => import("./features/plans"));
const Health = page(() => import("./features/health"));
const Audit = page(() => import("./features/audit"));

function ErrorPage() {
  const error = useRouteError();
  return (
    <main className="flex min-h-dvh items-center justify-center p-6 text-center">
      <div>
        <h1 className="text-lg font-semibold">Something went wrong</h1>
        <p className="mt-2 text-sm text-fg-subtle">
          {error instanceof Error ? error.message : "Unexpected error"}
        </p>
      </div>
    </main>
  );
}

function Lazy() {
  return (
    <Suspense fallback={<div className="h-64" aria-busy="true" />}>
      <Outlet />
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    element: <Lazy />,
    errorElement: <ErrorPage />,
    children: [
      { path: "/login", element: <Login /> },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <Shell />,
            children: [
              {
                element: <Lazy />,
                children: [
                  { index: true, element: <Overview /> },
                  { path: "/tenants", element: <Tenants /> },
                  { path: "/tenants/:id", element: <TenantDetail /> },
                  { path: "/plans", element: <Plans /> },
                  { path: "/health", element: <Health /> },
                  { path: "/audit", element: <Audit /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
]);
