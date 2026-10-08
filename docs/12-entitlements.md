# 12 · Subscription & Entitlement Architecture

> Covers §12 (plans, limits, feature access). Commercial values: [02 Business model](02-business-model.md). Tables: [07 §2.1](07-database-design.md#21-platform--commercial).

Goal: the code asks **"may tenant X do Y?"** and **"would this action exceed tenant X's limit Z?"** — and never asks "which plan is tenant X on?".

```python
# ❌ forbidden (CI grep rule rejects plan-code comparisons outside the entitlements module)
if tenant.plan == "pro": ...

# ✅
entitlements.require("custom_domain")
await entitlements.check_limit("max_students", delta=len(new_rows))
```

---

## 1. Model

```
features (catalogue)           plans                    plan_features
 key            kind            code      name           plan_id  feature_key        value
 max_students   limit           free      Free           free     max_students       150
 max_staff      limit           starter   Starter        free     custom_domain      false
 custom_domain  boolean         growth    Growth         pro      max_students       5000
 api_access     boolean         pro       Pro            pro      custom_domain      true
 history_years  limit           enterprise Enterprise    ent      max_students       null (unlimited → set per tenant)
 approval_modes enum-set        ...
                               tenant_subscriptions          tenant_feature_overrides
                                tenant_id plan_id status       tenant_id feature_key value  expires_at reason
                                                                abc       max_students 800  2026-12-31 "exam-season boost"
```

### Feature kinds
| Kind | Value type | Examples |
|---|---|---|
| `boolean` | true/false | `custom_branding`, `custom_domain`, `advanced_analytics`, `api_access`, `maker_checker_approval`, `remove_powered_by`, `sso`, `multiple_departments`, `multiple_campuses`, `custom_marksheet`, `scheduled_publication`, `automated_notifications` |
| `limit` | integer or `null` (= unlimited) | `max_students`, `max_staff`, `max_admins`, `max_storage_mb`, `history_years`, `max_published_exams_per_year`, `max_import_rows`, `email_notifications_per_month` |
| `enum_set` | list of allowed values | `marksheet_templates` (`["default"]` vs `["default","classic","modern"]`), `notification_channels` |

### Effective entitlement resolution
```
effective(tenant, key) =
    active, unexpired override for (tenant, key)        if exists
    else plan_features[active_subscription.plan, key]   if exists
    else features[key].default_value
```
Subscription status modifies the result:
| Status | Effect |
|---|---|
| `active`, `trialing` | plan values (the trial plan while `trialing`, §6) |
| `past_due` (grace, e.g. 14 days) | plan values + banner |
| `expired`/`cancelled` | fall back to **Free** values; nothing deleted (see downgrade rules) |
| tenant `suspended` | all tenant API access blocked except billing & export for owner |

---

## 2. Service interface

```python
class Entitlements(Protocol):
    def has(self, feature: str) -> bool: ...
    def require(self, feature: str) -> None: ...                 # raises FeatureNotInPlan (HTTP 402/403 problem)
    def limit(self, key: str) -> int | None: ...
    async def usage(self, key: str) -> int: ...
    async def check_limit(self, key: str, delta: int = 1) -> None:  # raises LimitExceeded with current/max
    def snapshot(self) -> dict[str, Any]: ...                    # for /tenant/config & /me (UI gating)
```
- Constructed per request from `TenantContext`; values cached (`t:{tid}:ent:v{n}`), version bumped whenever a subscription or override changes.
- FastAPI dependency: `Depends(require_feature("custom_domain"))` on routes; services also call it (jobs and internal paths are covered too).

---

## 3. Enforcing limits correctly (race conditions)

Naive `count(*) then insert` lets two concurrent imports both pass a 600-student limit. Pattern:

```sql
BEGIN;
SELECT value FROM tenant_usage_counters
 WHERE tenant_id = :t AND metric = 'active_students' FOR UPDATE;   -- serialises limit checks per tenant+metric
-- app: if value + :delta > limit → ROLLBACK + LimitExceeded
INSERT ... students ...;
UPDATE tenant_usage_counters SET value = value + :delta WHERE ...;
COMMIT;
```
- Counter updated in the same transaction as the change (archive → decrement).
- Nightly reconciliation job compares counters to real `count(*)` and alerts on drift (it should never drift; drift = bug).
- Limits that are *soft* (e.g. email volume) are checked without locking and enforced eventually.

### Enforcement points (non-exhaustive)
| Limit/feature | Checked at |
|---|---|
| `max_students` | student create, student import commit, un-archive |
| `max_staff`, `max_admins` | invite, role grant |
| `max_storage_mb` | upload (file size). Marksheet PDFs are **counted but never blocked** (P11.2): they're bounded by the student and publication caps already, and failing marksheets on result day would punish students for a plan matter. Uploads are refused once usage is over the cap |
| `history_years` | student/admin read of old publications → read-only archive notice beyond retention (data kept until retention policy says otherwise) |
| `max_published_exams_per_year` | publish |
| `custom_domain` | domain add & **every request on a custom host** (expired plan → redirect to subdomain) |
| `custom_branding` | branding save (fields beyond logo) and branding render (falls back to defaults) |
| `maker_checker_approval` | settings change & approval service |
| `api_access` | API key creation & API key auth |

---

## 4. Upgrade, downgrade, overage
- **Upgrade**: takes effect immediately (new subscription row, version bump → caches refresh).
- **Downgrade / expiry**: *never deletes data*. Over-limit tenants can view and export everything but cannot add more of the limited resource; premium presentation features fall back (custom domain → subdomain redirect, custom theme → default theme). Owner gets 30/14/7-day warnings before expiry.
- **Overage** (paid plans): optional tenant setting "allow overage" → instead of blocking at the limit, allow up to +10% and record overage for invoicing at renewal. Default: block with upgrade prompt.
- **Temporary boosts**: platform admin creates an override with `expires_at` (e.g. admission season) — audited in platform audit log.

## 5. Billing integration (phased)
| Phase | Approach |
|---|---|
| MVP | Plans/entitlements fully modelled; **billing is manual** (platform admin changes plan after bank transfer/UPI payment); invoices from accounting software. |
| V1 | Razorpay: payment links / checkout for annual plans, webhook → `tenant_subscriptions` update (idempotent by event id), GST invoice generation. |
| V2 | Recurring mandates for monthly plans if demand exists (RBI e-mandate constraints), proration, coupons. |

The entitlement system is independent of the payment provider — billing only writes subscription rows.

## 6. Free trial (30 days of Pro, once per institution)

**Offer.** The owner of an institution on the Free plan that has never had a paid plan can start one 30-day trial from *Plan & usage*. The trial plan (`trial`, not public) has every Pro feature except custom domain and API access, up to 1,000 students, 40 staff and 5 GB. No card is needed. The trial's subscription row is `trialing` with `period_end` = start + 30 days. When it ends, a `trials.end` job moves the tenant back to Free. If that job is late, entitlement resolution already treats a past `period_end` as expired. Nothing is deleted: over-limit data stays readable and exportable, but nothing more can be added until the institution upgrades (§4). The owner gets emails when the trial starts, 7 days and 1 day before it ends, and when it has ended.

**Once means once.** `tenant_trials` is unique per tenant and its rows are never deleted. Across tenants, the trial records *identity signals* in `trial_claims`: a global table with no tenant and no RLS, which the app role cannot read or write at all. Each signal is normalised, then hashed with HMAC-SHA256 under `SCORECODE_ABUSE_SIGNAL_KEY`, so the table holds digests only.

| Signal | Normalisation | Kind | Effect when seen before |
|---|---|---|---|
| Owner's email (verified at sign-up) | lower-case; drop `+tag`; Gmail ignores dots; `googlemail.com` → `gmail.com` | hard | refused |
| Owner's email domain, when it isn't a free mailbox provider | registrable part (`mail.school.edu.in` → `school.edu.in`) | hard | refused |
| Device id: a random, server-issued cookie scoped to the base domain, so the sign-up site and every portal share it | — | hard | refused |
| The tenant itself | — | hard | refused |
| Phone (sign-up form, institution settings; *not verified*) | digits with country code (`098765 43210` → `919876543210`) | soft | +1 risk |
| Institution name | ASCII, lower-case, punctuation dropped | soft | +1 risk |
| Network (/24 IPv4, /48 IPv6; private ranges ignored) | — | soft | +1 at 2 trials in 90 days, +2 at 4 |

- Hard signals can only be produced by their owner: the email is verified, the domain needs a mailbox there, the device id is set by our server. A match therefore refuses the trial.
- Soft signals can be typed by anyone, so on their own they never refuse. A competitor entering a school's phone number can't lock that school out. A score of **2 or more** sends the trial to a person: the owner is asked to write to support, and staff can start it from the platform console after checking (`POST /platform/tenants/{id}/trial`; still once per tenant).
- Concurrency: advisory locks on the hard digests serialise two attempts with the same identity, and a partial unique index on `(kind, digest)` for hard kinds is the last line of defence.
- Rate limits: trial starts per client IP (`SCORECODE_RATE_TRIAL_START_PER_HOUR`, default 5), on top of the existing sign-up limits.
- Every refusal is written to the platform audit log with the *kinds* of signal that matched, never the values. Every start is written to both audit logs, with its risk score and flags.

**Limits of this design.** Without a payment card, nobody can make free trials impossible to repeat. A person with several real mailboxes on different domains, fresh browsers, different networks and different institution names can still get another trial. The signals make that slow and visible, and the 1,000-student cap limits what a repeat trial is worth. Card verification and a phone OTP, once billing exists, are the next steps.

**Plan changes.** When staff move a tenant to a paid plan during the trial, the trial becomes `converted`; moving it back to Free makes it `revoked`. The end job then does nothing.

## 7. Testing
- Table-driven tests: (plan, overrides, status) → effective values.
- Concurrency test: two parallel imports racing for the last 10 seats → exactly one succeeds.
- Contract test: every `features.key` referenced in code exists in the catalogue (and vice versa, unused features flagged).
