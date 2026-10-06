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
| `active`, `trialing` | plan values |
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
| `max_storage_mb` | upload (file size), PDF generation (projected) |
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

## 6. Testing
- Table-driven tests: (plan, overrides, status) → effective values.
- Concurrency test: two parallel imports racing for the last 10 seats → exactly one succeeds.
- Contract test: every `features.key` referenced in code exists in the catalogue (and vice versa, unused features flagged).
