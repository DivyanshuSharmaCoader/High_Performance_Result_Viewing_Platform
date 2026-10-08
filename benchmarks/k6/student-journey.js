// Result-day student journey (docs/11 §4). One virtual user = one student:
//   config → me → latest result → class stats → (30%) history → think 2–10 s → repeat.
// The marksheet-URL step of the plan is left out: marksheet PDFs arrive in Phase 11.
//
// Run (stack up, data from backend/scripts/loadtest_data.py): benchmarks/k6/run.sh A preauth 1
// which wraps: docker run --rm --network scorecode_default -v "$PWD/benchmarks:/bench" grafana/k6 run \
//                -e SCENARIO=A -e VARIANT=preauth /bench/k6/student-journey.js
//
// SCENARIO: A (100 VUs: ramp 1 min, hold 5 min) | B (1,000 VUs: 0→1,000 in 60 s, hold 5 min)
// VARIANT:  preauth (sessions made beforehand) | cold (each VU signs in first: the Argon2 path)
import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
import exec from "k6/execution";

const BASE = __ENV.BASE_URL || "http://proxy:8080";
const HOST = __ENV.TENANT_HOST || "loadtest.localhost:8080";
const VARIANT = __ENV.VARIANT || "preauth";
const SCENARIO = __ENV.SCENARIO || "A";
const PASSWORD = "loadtest-student-pass";

const users = new SharedArray("users", () => JSON.parse(open(__ENV.USERS_FILE || "/bench/data/loadtest-users.json")));

const SHAPES = {
  smoke: { executor: "constant-vus", vus: 10, duration: "20s" },
  A: { executor: "ramping-vus", startVUs: 0, stages: [{ duration: "1m", target: 100 }, { duration: "5m", target: 100 }], gracefulRampDown: "15s" },
  B: { executor: "ramping-vus", startVUs: 0, stages: [{ duration: "60s", target: 1000 }, { duration: "5m", target: 1000 }], gracefulRampDown: "15s" },
};
const ENDPOINTS = ["config", "me", "latest", "stats", "history", "csrf", "login"];

export const options = {
  scenarios: { journey: SHAPES[SCENARIO] },
  summaryTrendStats: ["avg", "p(50)", "p(95)", "p(99)", "max"],
  // Always-true thresholds make k6 report every endpoint's latency separately.
  thresholds: Object.fromEntries(ENDPOINTS.map((n) => [`http_req_duration{name:${n}}`, ["max>=0"]])),
  discardResponseBodies: false,
  noCookiesReset: true, // a student stays signed in across iterations (k6 clears cookies by default)
};

function headers(vu) {
  // Each student on their own network address, from the range reserved for benchmarking (RFC 2544).
  const ip = `198.18.${(vu >> 8) & 255}.${vu & 255}`;
  // Caddy trusts the k6 container (a private address) to report it, and passes it on as X-Real-IP.
  return { Host: HOST, "X-Forwarded-For": ip, Accept: "application/json" };
}

function get(path, name, h) {
  const r = http.get(`${BASE}${path}`, { headers: h, tags: { name } });
  check(r, { [`${name} 200`]: (x) => x.status === 200 });
  return r;
}

export default function () {
  const vu = exec.vu.idInTest;
  const user = users[(vu - 1) % users.length];
  const h = headers(vu);
  if (exec.vu.iterationInScenario === 0) {
    if (VARIANT === "cold") {
      const csrf = http.get(`${BASE}/api/v1/auth/csrf`, { headers: h, tags: { name: "csrf" } });
      const token = csrf.cookies["sc_csrf"] ? csrf.cookies["sc_csrf"][0].value : "";
      const login = http.post(
        `${BASE}/api/v1/auth/login`,
        JSON.stringify({ login_id: user.login, password: PASSWORD }),
        { headers: { ...h, "Content-Type": "application/json", "X-CSRF-Token": token }, tags: { name: "login" } },
      );
      check(login, { "login 200": (x) => x.status === 200 });
    } else {
      // k6 keeps a cookie jar per VU: put the pre-made session in it once.
      http.cookieJar().set(BASE, "sc_session", user.token);
    }
  }
  get("/api/v1/tenant/config", "config", h);
  get("/api/v1/me", "me", h);
  const latest = get("/api/v1/me/results/latest", "latest", h);
  const pub = latest.status === 200 && latest.json() ? latest.json().publication_id : null;
  if (pub) get(`/api/v1/me/results/${pub}/stats`, "stats", h);
  if (Math.random() < 0.3) get("/api/v1/me/results", "history", h);
  sleep(2 + Math.random() * 8);
}

export function handleSummary(data) {
  const out = __ENV.SUMMARY || `/bench/results/runs/k6-${SCENARIO}-${VARIANT}-${Date.now()}.json`;
  return { [out]: JSON.stringify(data, null, 1), stdout: textSummary(data) };
}

function textSummary(data) {
  const m = data.metrics;
  const lines = [`scenario ${SCENARIO} · ${VARIANT}`];
  const reqs = m.http_reqs ? m.http_reqs.values : {};
  lines.push(`requests ${reqs.count} · ${Number(reqs.rate || 0).toFixed(1)}/s · failed ${(100 * (m.http_req_failed ? m.http_req_failed.values.rate : 0)).toFixed(2)}%`);
  for (const n of ENDPOINTS) {
    const t = m[`http_req_duration{name:${n}}`];
    if (!t || !t.values || t.values.max === undefined || t.values.max === 0) continue;
    const v = t.values;
    lines.push(`${n.padEnd(8)} p50=${v["p(50)"].toFixed(1)}ms p95=${v["p(95)"].toFixed(1)}ms p99=${v["p(99)"].toFixed(1)}ms max=${v.max.toFixed(0)}ms`);
  }
  for (const [name, c] of Object.entries(data.root_group.checks || {})) {
    lines.push(`check ${c.name}: ${c.passes} ok, ${c.fails} failed`);
  }
  return lines.join("\n") + "\n";
}
