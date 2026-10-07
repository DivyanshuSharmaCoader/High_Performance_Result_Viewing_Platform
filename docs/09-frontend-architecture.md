# 09 · Frontend Architecture

> Covers brief section **K**, §22–25 (frontend, student, admin and platform-admin experiences) and §17 (data-driven branding).

The old frontend is discarded. We start from **information architecture and user journeys**, then derive apps, routes and components.

---

## 1. Applications and why they are split this way

| App | Host | Users | Rendering | Why separate |
|---|---|---|---|---|
| **Tenant app** (`apps/tenant`) | `<slug>.scorecode.in` / custom domain | Students, faculty, institution admins | SPA (Vite + React), role-based code splitting | One origin per tenant; student and staff share login and branding; **route-level code splitting** keeps the student bundle tiny (admin grid code never downloaded by students). |
| **Platform console** (`apps/platform`) | `admin.scorecode.in` | ScoreCode staff | SPA | Different auth realm, different security posture (2FA, IP allow-list optional); must never share an origin with tenant content. |
| **Marketing & sign-up** (`apps/site`) | `scorecode.in` | Prospects | Static site (Astro or plain Vite SSG) | SEO, fast, no app JS. |
| **Verification page** | `verify.scorecode.in` | Anonymous verifiers | **Server-rendered HTML** from the backend (Jinja), ~0 JS | Must be instant on any phone, simple to audit, no SPA needed. |

### SPA vs SSR (Next.js) for the tenant app
| | Vite SPA on CDN | Next.js SSR |
|---|---|---|
| Result-day load on our servers | Only API calls; HTML/JS from CDN | Every page render hits Node servers |
| Infra | Static hosting | Node runtime to scale |
| SEO need | None (logged-in app) | — |
| **Verdict** | ✅ Chosen | Not justified |

---

## 2. Information architecture & navigation

### Student (mobile-first, bottom tab bar on mobile, sidebar on desktop)
```
Home (latest result card, notifications preview)
├── Results ── list of publications (newest first)
│      └── Result detail ── papers, totals, grade, status, "Revised" badge
│             ├── Download marksheet
│             └── Statistics (only what institution allows)
├── Notifications
└── Profile (details, change password, sessions/log out everywhere)
```
Target: **result in ≤ 2 taps after login**; dashboard works on a 360 px-wide screen.

### Faculty
```
My papers (assigned papers × cohorts with status chips: Open / Submitted / Returned / Locked)
└── Marks grid → Submit
Statistics (assigned papers only)
Profile
```

### Institution admin
```
Dashboard (setup checklist, exams in progress, recent activity, plan usage)
People ── Students · Staff & roles
Academics ── Sessions & terms · Departments · Programs · Cohorts · Courses
Exams ── list → Exam workspace (tabs):
           Setup (papers, cohorts, grading) · Marks (progress matrix) · Imports
           · Processing & preview · Approval · Publication (history, corrections)
Analytics
Notifications (templates, sent log)
Settings ── Institution · Branding · Grading schemes · Security · Domain
Subscription & usage
Audit log
```
Design note: the **Exam workspace** is the centre of gravity — admins live there during result season; every step of W5–W15 is a tab with a clear "next step" call-to-action.

### Platform console
```
Overview (tenants by plan/status, students, publications this week, errors, p95, cache hit rate, queue depth)
Tenants → tenant detail (plan, usage, domains, overrides, suspend, support session)
Plans & features
System health (dependencies, job queues, recent errors)
Platform audit log
```

---

## 3. Tech stack (frontend)

| Concern | Choice | Alternatives considered | Reason |
|---|---|---|---|
| Language | TypeScript (strict) | JS | Type safety end-to-end with generated API types |
| Build | Vite | webpack, Next.js | Fast, simple, static output |
| Routing | React Router (data routers, lazy routes) | TanStack Router | Mature, lazy route modules for code splitting |
| Server state | **TanStack Query** | Redux, SWR | Caching, retries, dedup, background refetch — most "state" is server state |
| Client state | React state + small Zustand store only if needed | Redux | Little genuine global client state (theme, UI prefs) |
| Forms & validation | react-hook-form + zod | Formik | Performance on large forms; zod schemas mirror API |
| API client | Generated types from `openapi.json` (`openapi-typescript`) + thin `fetch` wrapper | Hand-written | Contract drift caught at compile time |
| UI primitives | Radix UI primitives + Tailwind CSS (shadcn/ui-style, copied into repo) | MUI, Chakra | Accessible primitives, themeable via CSS variables, no heavy runtime |
| Data grid (marks) | TanStack Table + custom virtualised editable grid (or AG Grid Community if time-boxed) | Handsontable (licensing) | Keyboard-first entry, paste from Excel, 1,000+ rows virtualised |
| Charts | Recharts or Visx (admin analytics only, lazy-loaded) | Chart.js | React-friendly; loaded only on analytics routes |
| i18n | i18next (English first; Hindi later) | — | Indian market will ask for it; keep strings externalised from day one |
| Testing | Vitest + React Testing Library; Playwright E2E; axe-core accessibility checks | Jest, Cypress | Fast, modern |

---

## 4. Monorepo layout (frontend part)

```
frontend/
  apps/
    tenant/        # student + faculty + institution admin
    platform/      # ScoreCode console
    site/          # marketing + sign-up
  packages/
    ui/            # design system: tokens, primitives, composite components
    api-client/    # generated OpenAPI types + fetch wrapper + query keys
    config/        # eslint, tsconfig, tailwind preset
  pnpm-workspace.yaml
```

---

## 5. Design system

### Tokens (CSS custom properties, the only thing branding changes)
```css
:root {
  --sc-color-primary: #2952cc;      /* tenant overridable */
  --sc-color-primary-contrast: #fff;/* computed server-side for WCAG AA */
  --sc-color-secondary: #0f766e;    /* tenant overridable */
  --sc-color-bg, --sc-color-surface, --sc-color-text, --sc-color-muted,
  --sc-color-success, --sc-color-warning, --sc-color-danger;  /* fixed — semantic colours are NOT brandable */
  --sc-font-sans: "Inter", system-ui, sans-serif;  /* tenant picks from allow-list */
  --sc-radius-sm/md/lg, --sc-space-1..10, --sc-shadow-1..3;
}
```
Rule: tenants can change **brand** tokens; **semantic** tokens (pass/fail colours, error states) stay fixed so meaning is consistent and accessible.

### Shared components (`packages/ui`)
Primitives: Button, Input, Select, Checkbox, Dialog, Sheet, Tabs, Toast, Tooltip, Badge, Card, Table, Skeleton, EmptyState, Pagination.
Composites: `AppShell` (role-aware nav), `TenantLogo`, `ResultCard`, `ResultTable`, `GradeBadge`, `StatusChip` (state machine states), `FileDropzone`, `ImportIssuesTable`, `MarksGrid`, `ProgressMatrix`, `ConfirmWithReasonDialog` (used for publish/withdraw/unlock — always captures a reason for the audit log), `LimitBanner` (entitlement usage), `FeatureGate` (renders upgrade prompt when feature missing), `AuditTimeline`.

### Accessibility & responsiveness
- WCAG 2.1 AA target; automated axe checks in E2E; brand colours validated for contrast on save (server rejects or auto-adjusts contrast colour).
- Breakpoints: mobile-first (360 px), tablet (768), desktop (1024+). Student app optimised for mobile; admin optimised for desktop but usable on tablet; marks grid is desktop-only with a mobile "view only" fallback.

---

## 6. Tenant-aware bootstrapping & branding

```
1. Browser loads https://abc.scorecode.in/  → index.html + hashed JS/CSS from CDN (same for all tenants)
2. App calls GET /api/v1/tenant/config  (cached by browser via ETag; cached server-side)
      → { name, logo_url, favicon_url, tokens:{primary,...}, font, login_heading, footer, features:{...} }
3. App sets CSS variables on :root, favicon, document.title — before first meaningful paint
   (small inline script + skeleton avoids flash of default theme)
4. GET /api/v1/me → principal & roles → route tree for the role
```
- **One build for all tenants** — no per-customer frontend codebase or build.
- Unknown tenant → config returns 404 → static "institution not found" page.
- Feature flags from config drive `FeatureGate` (UI only — **backend still enforces**).

## 7. Routing & role guards
- Route trees: `/` (role home redirect), `/results/*` (student), `/faculty/*`, `/admin/*`.
- Guards are UX only; every API call is authorized server-side.
- Lazy-loaded route modules per role: student initial JS budget **< 150 kB gzipped**, **enforced in CI** (`apps/tenant/scripts/check-bundle.mjs`). The check follows the Vite manifest and counts the entry, everything it imports statically, and the student home route. Measured at 139.9 kB on 2026-10-08, down from 185 kB. What got it there:
  - the staff shell is lazy, so students never download admin navigation;
  - the UI package is marked side-effect-free, so it tree-shakes per route;
  - the re-auth dialog loads only when an action asks for a password;
  - the toaster loads right after first paint;
  - the student account menu is a small disclosure, not the positioning-engine menu.
- The student portal (`/me`, `/me/results/{publication}`) renders the published snapshot through `StudentResultView`. The admin preview on the Results tab uses the same component with a snapshot-shaped payload built from the run (`features/results/preview.ts`), so what is approved is what students see.

## 8. Data fetching & caching rules
- Query keys always include the resource identity; **tenant isolation on the client is provided by the origin** (each tenant is a separate origin, so caches/localStorage never mix).
- Published results: `staleTime: Infinity` (immutable per publication version).
- Lists: `staleTime` 30 s; mutations invalidate precise keys.
- Long jobs: poll `GET /jobs/{id}` every 2 s with backoff (SSE later — [11](11-performance-architecture.md#29-real-time-updates-websockets-vs-sse-vs-polling)).
- No sensitive data in `localStorage`; session is an HttpOnly cookie (JS cannot read it).

## 9. Result-day resilience in the UI
- If the API returns 429/503: friendly "Results are being published — retrying in N s" with automatic jittered retry (prevents synchronized retry storms).
- Skeletons, not spinners; result card designed to render from the single `/me/results/latest` payload.
- Marksheet button disabled with "Preparing…" if the PDF isn't rendered yet.
