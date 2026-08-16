/**
 * D-4 (orchestrator/DISPATCH-2.md §6, ADR-003 §5 / D-17): the session
 * token must never be written to localStorage/sessionStorage — one XSS and
 * everything is stolen. Real persistence is httpOnly cookie + refresh,
 * which requires a /backend endpoint that doesn't exist yet
 * (console/RECONCILIATION.md §8); until then the session lives in React
 * state only and is lost on refresh, which is the honest state to be in.
 *
 * Static-scans the actual source tree rather than asserting behavior of a
 * mocked browser API, so it fails the moment anyone adds either call
 * anywhere under src/ — including files this session didn't touch.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(here, "..", "src");

function walk(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else if (/\.(ts|tsx)$/.test(entry.name)) out.push(full);
  }
  return out;
}

test("no source file under console/src writes to localStorage or sessionStorage", () => {
  // Matches actual API usage (localStorage.setItem(...), window.sessionStorage[...])
  // — not prose mentions in doc comments explaining why NOT to use it (a
  // sentence ending "...localStorage." has a period too, so this requires
  // an identifier or bracket right after the dot, not just any '.').
  const USAGE = /\b(localStorage|sessionStorage)(\.[a-zA-Z_$]|\[)/;
  const offenders = [];
  for (const file of walk(SRC)) {
    const text = fs.readFileSync(file, "utf8");
    if (USAGE.test(text)) {
      offenders.push(path.relative(path.resolve(here, ".."), file));
    }
  }
  assert.deepEqual(offenders, [], `token/session must stay in React state only (ADR-003 §5): ${offenders.join(", ")}`);
});
