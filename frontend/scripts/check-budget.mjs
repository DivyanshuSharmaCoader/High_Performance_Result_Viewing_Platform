// Reports gzipped JavaScript size per app entry (initial load = entry chunk + its static imports).
// docs/09 §7: student initial JS budget < 150 KB gz — enforced from P10.5 (student portal); reported until then.
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const ENFORCE = process.env.BUDGET_ENFORCE === "1";
const BUDGET_KB = 150;
let failed = false;
for (const app of readdirSync("apps")) {
  const dist = join("apps", app, "dist");
  if (!existsSync(join(dist, "index.html"))) continue;
  const html = readFileSync(join(dist, "index.html"), "utf8");
  const entry = [...html.matchAll(/src="\/(assets\/[^"]+\.js)"/g)].map((m) => m[1]);
  const preload = [...html.matchAll(/href="\/(assets\/[^"]+\.js)"/g)].map((m) => m[1]);
  const files = [...new Set([...entry, ...preload])];
  const kb = files.reduce((sum, f) => sum + gzipSync(readFileSync(join(dist, f))).length, 0) / 1024;
  const all = readdirSync(join(dist, "assets")).filter((f) => f.endsWith(".js"));
  const totalKb = all.reduce((s, f) => s + statSync(join(dist, "assets", f)).size, 0) / 1024;
  const over = kb > BUDGET_KB;
  if (over && ENFORCE) failed = true;
  console.log(`${app}: initial JS ${kb.toFixed(1)} KB gz (${files.length} files)${over ? ` — over ${BUDGET_KB} KB` : ""}; all chunks ${totalKb.toFixed(0)} KB raw`);
}
process.exit(failed ? 1 : 0);
