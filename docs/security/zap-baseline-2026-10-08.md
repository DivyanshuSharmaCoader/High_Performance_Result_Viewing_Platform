# ZAP baseline scan — 2026-10-08 (P15.4)

**Run:** `dast.yml` run 37741788953 on commit 33f21a9. This is ZAP's passive baseline scan (`zap-baseline.py`,
3-minute spider) against the full container stack on a GitHub runner, with demo tenants seeded. The
reports are the `zap-37741788953` artifact, kept for 30 days.

**Targets:**
- `thapar.localhost/login`: the tenant SPA and its API.
- `verify.localhost/v`: the server-rendered verification page.
- `localhost/`: the marketing site.
- `admin.localhost/login`: the platform console.

## Result: no High alerts, one Medium
| Risk | Alert (plugin) | Where | Disposition |
|---|---|---|---|
| Medium | CSP: `style-src 'unsafe-inline'` (10055) | all four hosts | **Verify page: fixed.** Its one stylesheet is pinned by SHA-256 and its last `style=""` attribute removed (`test_the_public_verify_page` checks the hash against the rendered page). **SPAs: accepted risk R-CSP** (docs/10 §5). Two dependencies insert `<style>` elements at run time, and scripts remain `'self'`-only. |
| Low | Cross-Origin-Embedder-Policy missing (90004) | all four | **Fixed.** `credentialless` on the SPAs (cross-origin logos still load), `require-corp` on the verify page. |
| Low | Cross-Origin-Opener-Policy missing (90004) | tenant, site, console | **Fixed.** `same-origin` at the edge, as a default. |
| Low | Cross-Origin-Resource-Policy missing (90004) | tenant, site, console | **Fixed.** `same-origin` at the edge, as a default. |
| Info | Storable and cacheable content (10049) | `/`, `/login` on the SPAs | **Fixed, and it was a real reliability bug.** The edge's `no-cache` matched only the literal path `/index.html`. So the HTML served under app routes could be cached heuristically and, after a deploy, point at assets that no longer exist. Now every non-asset response is `no-cache`, and a missing asset is 404 `no-store` instead of `index.html`. |
| Info | Suspicious comments (10027) | SPA bundles | **False positive.** An error message string inside react-router. |
| Info | Modern web application (10109) | SPAs | Informational only. |

## Found while analysing it
The edge's header block was applied as the response was written, so it **overwrote the API's own
headers**. On the verify host that replaced `Referrer-Policy: no-referrer` (the verification code is in
the address) with `strict-origin-when-cross-origin`.

The exposure was limited: cross-origin destinations would still only have received the origin. But the
designed policy wasn't the one being sent. The edge's `Referrer-Policy`, `Permissions-Policy`, COOP and
CORP are now **defaults** (`?` in Caddy, one directive each). `e2e/edge.spec.ts` checks the verify page's
own value against the real proxy.

## Checked how
- A local run of the proxy image with the changed Caddyfile and a stand-in upstream, checking the headers
  of SPA routes, a hashed asset, a removed asset, and verify and API responses.
- `e2e/edge.spec.ts` in CI against the full stack. It also checks that Chromium reports no CSP violations
  on the verify page and the tenant login, that the verify stylesheet applies, and that the tenant page is
  `crossOriginIsolated`.
- The next scheduled `dast.yml` run (Mondays) should show only the accepted `style-src` alert on the SPAs.
