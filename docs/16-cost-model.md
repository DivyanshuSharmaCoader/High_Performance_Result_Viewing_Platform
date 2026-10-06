# 16 · Infrastructure Cost Model

> Covers brief section **R** and §33 (cost optimisation).
> ⚠️ **All figures are rough estimates based on typical public list prices of common providers at the time of writing, converted at ~₹85–90 per USD. Cloud prices change; re-check the provider calculators before committing.** They exist to show *orders of magnitude* and to keep the architecture honest about cost, not as quotes.

---

## 1. Cost drivers (what actually costs money)

| Driver | Scales with | Notes |
|---|---|---|
| Compute (API + workers) | Peak concurrency, PDF rendering | Mostly idle outside publication spikes → right-size + pre-scale for scheduled publications instead of permanently large machines |
| PostgreSQL | Data size (small), HA requirement | Managed HA roughly doubles DB cost; worth it once customers pay |
| Redis | Small memory footprint | Optional at small scale |
| Object storage | PDFs, uploads, exports | Cheap per GB; **egress** is the hidden cost → Cloudflare R2 (no egress fees) or CDN in front of S3 |
| Bandwidth | Static assets (CDN), PDFs | CDN free tiers cover early stages |
| Backups | DB size × retention | Small |
| Logs/monitoring | Log volume | Easily becomes the largest line item if unmanaged — keep retention short, sample debug logs, use free tiers |
| Email | Notifications | Amazon SES is roughly $0.10 per 1,000 emails; other providers have free tiers then monthly plans |
| SMS/WhatsApp | Per message | India: requires DLT registration for SMS; per-message cost is non-trivial at scale → **pass-through billing only** |
| Domains/TLS | Fixed | `.in` domain ~₹500–1,000/year; TLS free (Let's Encrypt) |
| Error tracking | Events | Sentry free tier initially, or self-hosted GlitchTip |

---

## 2. Stage estimates (monthly)

### Demo / pilot (≤ 3 tenants, college presentation)
| Item | Choice | ~USD/mo | ~INR/mo |
|---|---|---|---|
| VM 2 vCPU / 4 GB, Indian region | DigitalOcean/Lightsail/Hetzner-class | 12–24 | 1,000–2,100 |
| DB, Redis, MinIO | on the same VM | 0 | 0 |
| Backups → object storage | R2/S3 (few GB) | 0–2 | 0–170 |
| CDN/DNS/TLS | Cloudflare free | 0 | 0 |
| Email | SES / free tier | ~0 | ~0 |
| Domain | `.in` / `.app` | ~1 (amortised) | ~80 |
| **Total** | | **~15–30** | **~₹1.3k–2.6k** |

### Small production (≈ 10–100 tenants, up to ~50k students total)
| Item | Choice | ~USD/mo | ~INR/mo |
|---|---|---|---|
| 2 × app VMs (2 vCPU / 4 GB) | API + worker | 40–60 | 3.5k–5.3k |
| Managed PostgreSQL, small, with standby | DO/Azure/Lightsail-class (AWS RDS Multi-AZ costs more) | 30–120 | 2.6k–10.5k |
| Redis | self-hosted on app VM → managed later | 0–15 | 0–1.3k |
| Object storage + backups | R2/S3, tens of GB | 2–10 | 170–900 |
| Monitoring/logging | Grafana Cloud/Better Stack free tiers + Sentry free | 0–30 | 0–2.6k |
| Email | ~50k emails/month on SES | ~5 | ~450 |
| Load balancer | Caddy on VMs, or managed LB | 0–15 | 0–1.3k |
| **Total** | | **~80–250** | **~₹7k–22k** |

### Growing production (hundreds of tenants, ~200k–500k students)
Autoscaled containers, larger managed DB + read replica, managed Redis, PgBouncer, more monitoring: **roughly $500–1,500/month (₹45k–1.3L)** depending heavily on provider and whether AWS-managed services are used. Only reached when revenue is far larger than this.

---

## 3. Does it make economic sense?

Using the proposed plans ([02](02-business-model.md)):
- Small production at ~₹15k/month ≈ **₹1.8 L/year** infra.
- Break-even on infra alone ≈ **10 Growth customers** or **~23 Starter customers** (before GST, payment fees, support, salaries).
- Marginal infra cost of one more small tenant is tiny (storage + emails + some PDF CPU): on the order of **tens of rupees per month** for a few hundred students — which is why a free tier is affordable, *provided the free tier doesn't generate support load*.

**Conclusion:** the architecture is cost-appropriate. The constraint on profitability is **people time (sales, onboarding, support)**, not infrastructure. That's why import UX, self-serve onboarding and documentation are business-critical features.

## 4. Cost-control rules baked into the architecture
1. One database for all shared tenants; no per-tenant infrastructure below Enterprise.
2. Static frontend on CDN — app servers only serve API.
3. PDFs pre-rendered once, stored, served from object storage/CDN (no repeated CPU).
4. No always-on large instances; pre-scale for *scheduled* publication windows.
5. Log retention short; metrics over logs; sample traces.
6. Free-tier limits that bound resource use (students, storage, emails, publications/year).
7. SMS/WhatsApp only as pass-through paid add-ons.
8. Enterprise dedicated deployments priced at ≥2–3× their infra cost plus ops fee.
