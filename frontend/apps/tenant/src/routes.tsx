import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from "react";
import { Navigate, Outlet, createBrowserRouter } from "react-router";

import { ReauthProvider } from "./components/reauth";
import { StaffShell } from "./components/staff-shell";
import { BootSplash, NotFound, RouteError } from "./components/system-pages";
import { RequireAuth, RequirePermission, homePathFor, useSession } from "./lib/session";
import { TenantProvider } from "./lib/tenant";

// Route-level code splitting: students never download admin code (docs/09 §7).
const page = (load: () => Promise<{ default: ComponentType }>) => lazy(load);
const Login = page(() => import("./features/auth/login"));
const Activate = page(() => import("./features/auth/activate"));
const Forgot = page(() => import("./features/auth/forgot"));
const Reset = page(() => import("./features/auth/reset"));
const AcceptInvite = page(() => import("./features/auth/accept-invite"));
const Welcome = page(() => import("./features/auth/welcome"));
const Dashboard = page(() => import("./features/admin/dashboard"));
const Staff = page(() => import("./features/admin/staff"));
const Plan = page(() => import("./features/admin/plan"));
const Audit = page(() => import("./features/admin/audit"));
const Account = page(() => import("./features/account/account"));
const AcademicsLayout = page(() => import("./features/academics/layout"));
const Sessions = page(() => import("./features/academics/sessions"));
const Departments = lazy(() =>
  import("./features/academics/catalog").then((m) => ({ default: m.DepartmentsPage })),
);
const Programs = lazy(() =>
  import("./features/academics/catalog").then((m) => ({ default: m.ProgramsPage })),
);
const Cohorts = lazy(() => import("./features/academics/catalog").then((m) => ({ default: m.CohortsPage })));
const Courses = lazy(() => import("./features/academics/catalog").then((m) => ({ default: m.CoursesPage })));
const SettingsLayout = lazy(() =>
  import("./features/admin/settings").then((m) => ({ default: m.SettingsLayout })),
);
const InstitutionSettings = lazy(() =>
  import("./features/admin/settings").then((m) => ({ default: m.InstitutionSettingsPage })),
);
const BrandingSettings = lazy(() =>
  import("./features/admin/branding").then((m) => ({ default: m.BrandingSettingsPage })),
);

function load(Component: LazyExoticComponent<ComponentType>) {
  return (
    <Suspense fallback={<BootSplash />}>
      <Component />
    </Suspense>
  );
}

function Root() {
  return (
    <TenantProvider>
      <ReauthProvider>
        <Outlet />
      </ReauthProvider>
    </TenantProvider>
  );
}

function Home() {
  return <Navigate to={homePathFor(useSession())} replace />;
}

function Shell() {
  return (
    <StaffShell>
      <Suspense fallback={<div className="h-96" aria-busy="true" />}>
        <Outlet />
      </Suspense>
    </StaffShell>
  );
}

export const router = createBrowserRouter([
  {
    element: <Root />,
    errorElement: <RouteError />,
    children: [
      { path: "/login", element: load(Login) },
      { path: "/activate", element: load(Activate) },
      { path: "/forgot-password", element: load(Forgot) },
      { path: "/reset-password", element: load(Reset) },
      { path: "/accept-invite", element: load(AcceptInvite) },
      { path: "/welcome", element: load(Welcome) },
      {
        element: <RequireAuth />,
        children: [
          { index: true, element: <Home /> },
          {
            element: <Shell />,
            children: [
              { path: "/account", element: <Account /> },
              {
                path: "/admin",
                children: [
                  {
                    element: <RequirePermission permission="students.view" />,
                    children: [{ index: true, element: <Dashboard /> }],
                  },
                  {
                    element: <RequirePermission permission="staff.view" />,
                    children: [{ path: "staff", element: <Staff /> }],
                  },
                  {
                    element: <RequirePermission permission="subscription.view" />,
                    children: [{ path: "plan", element: <Plan /> }],
                  },
                  {
                    element: <RequirePermission permission="audit.view" />,
                    children: [{ path: "audit-log", element: <Audit /> }],
                  },
                  {
                    element: <RequirePermission permission="academics.view" />,
                    children: [
                      {
                        path: "academics",
                        element: <AcademicsLayout />,
                        children: [
                          { index: true, element: <Sessions /> },
                          { path: "departments", element: <Departments /> },
                          { path: "programs", element: <Programs /> },
                          { path: "cohorts", element: <Cohorts /> },
                          { path: "courses", element: <Courses /> },
                        ],
                      },
                    ],
                  },
                  {
                    element: <RequirePermission permission="settings.manage" />,
                    children: [
                      {
                        path: "settings",
                        element: <SettingsLayout />,
                        children: [
                          { index: true, element: <InstitutionSettings /> },
                          { path: "branding", element: <BrandingSettings /> },
                        ],
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
