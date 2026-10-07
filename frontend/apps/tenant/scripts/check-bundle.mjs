// The student first-load budget (docs/09 §7, P10.5): the JavaScript a student downloads before seeing
// their results — the app entry, everything it imports statically, and the student home route — must stay
// under BUDGET gzipped. Run after `vite build`; exits non-zero when over.
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const BUDGET = 150_000; // bytes, gzipped (Vite's "kB")
const ROUTES = ["src/features/student/home.tsx", "src/components/student-shell.tsx"];
const dist = path.resolve(import.meta.dirname, "../dist");
const manifest = JSON.parse(fs.readFileSync(path.join(dist, ".vite/manifest.json"), "utf8"));

const gz = (file) => zlib.gzipSync(fs.readFileSync(path.join(dist, file)), { level: 9 }).length;
const loaded = new Map(); // file → gzipped bytes

function take(key) {
  const item = manifest[key];
  if (!item || loaded.has(item.file)) return;
  loaded.set(item.file, gz(item.file));
  for (const dep of item.imports ?? []) take(dep);
}

const entry = Object.keys(manifest).find((k) => manifest[k].isEntry);
take(entry);
const initial = new Set(loaded.keys());
for (const route of ROUTES) take(route);

const rows = [...loaded].sort((a, b) => b[1] - a[1]);
const total = rows.reduce((n, [, b]) => n + b, 0);
for (const [file, bytes] of rows) {
  console.log(
    `${(bytes / 1000).toFixed(1).padStart(7)} kB  ${initial.has(file) ? "entry" : "route"}  ${file}`,
  );
}
console.log(`${(total / 1000).toFixed(1).padStart(7)} kB  total (budget ${(BUDGET / 1000).toFixed(0)} kB)`);
if (total > BUDGET) {
  console.error(`Student first load is over budget by ${((total - BUDGET) / 1000).toFixed(1)} kB.`);
  process.exit(1);
}
