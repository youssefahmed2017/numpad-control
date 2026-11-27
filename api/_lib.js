// Shared code of the crash-report API. Plain functions, no framework, so the tests can call them
// with a fake database: handleX(request, sql, env) -> Response.

import { createHash, timingSafeEqual } from "node:crypto";

export const MAX_BODY = 20000;        // bytes of a report we accept
export const MAX_PER_HOUR = 10;       // reports from one address per hour
export const STATUSES = ["open", "fixed", "wontfix", "duplicate", "hidden"];
export const KINDS = ["bug", "feature", "question"];
export const MAX_FEEDBACK_PER_HOUR = 3;  // problem reports typed by hand, per address

const LIMITS = { component: 40, version: 40, system: 200, python: 20, error: 300, traceback: 6000, note: 1000 };

export function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
  });
}

// Control characters (except newline and tab) and text-direction tricks are taken out of every text.
function clean(text, max) {
  return String(text)
    .replace(/[\u0000-\u0008\u000b-\u001f\u007f‪-‮⁦-⁩]/g, "")
    .slice(0, max);
}

/** A problem report typed on the website: {feedback} to keep, {ignore: true} for a bot, or {error}. */
export function validateFeedback(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { error: "a JSON object is expected" };
  for (const name of ["kind", "title", "body"]) if (typeof body[name] !== "string") return { error: `${name} is missing` };
  if (body.contact !== undefined && typeof body.contact !== "string") return { error: "contact must be text" };
  // Bots fill in the hidden field and send at once: they are told "ok" and nothing is saved.
  if (body.website || !(Number(body.elapsed) >= 2500)) return { ignore: true };
  if (!KINDS.includes(body.kind)) return { error: "kind is not valid" };
  const title = clean(body.title, 120).trim(), text = clean(body.body, 3000).trim(), contact = clean(body.contact || "", 200).trim();
  if (title.length < 5) return { error: "the title is too short (at least 5 characters)" };
  if (text.length < 10) return { error: "please say a little more (at least 10 characters)" };
  if (((title + text).match(/https?:\/\//gi) || []).length > 2) return { error: "at most 2 links, please" };
  return { feedback: { kind: body.kind, title, body: text, contact } };
}

/** The report as we keep it, or an error string. Only the fields below are ever kept. */
export function validate(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { error: "a JSON object is expected" };
  const out = {};
  for (const [name, max] of Object.entries(LIMITS)) {
    const value = body[name];
    if (value === undefined || value === null || value === "") {
      if (name === "note") { out.note = ""; continue; }
      return { error: `${name} is missing` };
    }
    if (typeof value !== "string") return { error: `${name} must be text` };
    out[name] = clean(value, max);
  }
  if (!/^[a-z0-9_-]{1,40}$/.test(out.component)) return { error: "component is not valid" };
  if (typeof body.signature !== "string" || !/^[0-9a-f]{12}$/.test(body.signature)) return { error: "signature is not valid" };
  out.signature = body.signature;
  return { report: out };
}

export function clientAddress(request) {
  return (request.headers.get("x-forwarded-for") || "").split(",")[0].trim() || "unknown";
}

/** Addresses are never stored: only a hash that changes every day, to count reports per hour. */
export function addressHash(address, env, day = new Date().toISOString().slice(0, 10)) {
  return createHash("sha256").update(`${env.RATE_SALT || ""}|${day}|${address}`).digest("hex").slice(0, 32);
}

let ready;
/** Creates the tables the first time (every instance, once). */
export async function ensureTables(sql) {
  ready ??= (async () => {
    await sql`CREATE TABLE IF NOT EXISTS crash_issues (
      signature text PRIMARY KEY, title text NOT NULL, component text NOT NULL, traceback text NOT NULL,
      status text NOT NULL DEFAULT 'open', fixed_in text, count integer NOT NULL DEFAULT 1,
      first_seen timestamptz NOT NULL DEFAULT now(), last_seen timestamptz NOT NULL DEFAULT now())`;
    await sql`CREATE TABLE IF NOT EXISTS crash_reports (
      id bigserial PRIMARY KEY, signature text NOT NULL, version text NOT NULL, system text NOT NULL,
      python text NOT NULL, note text NOT NULL DEFAULT '', created timestamptz NOT NULL DEFAULT now())`;
    await sql`CREATE TABLE IF NOT EXISTS crash_rate (h text NOT NULL, t timestamptz NOT NULL DEFAULT now())`;
    await sql`CREATE TABLE IF NOT EXISTS feedback (
      id bigserial PRIMARY KEY, kind text NOT NULL, title text NOT NULL, body text NOT NULL, contact text NOT NULL DEFAULT '',
      status text NOT NULL DEFAULT 'open', fixed_in text, created timestamptz NOT NULL DEFAULT now())`;
    await sql`CREATE INDEX IF NOT EXISTS crash_rate_h ON crash_rate (h, t)`;
    await sql`CREATE INDEX IF NOT EXISTS crash_reports_sig ON crash_reports (signature)`;
  })().catch((error) => { ready = undefined; throw error; });
  return ready;
}

export function resetForTests() { ready = undefined; }

export function sameSecret(given, wanted) {
  const a = Buffer.from(String(given)), b = Buffer.from(String(wanted));
  return a.length === b.length && timingSafeEqual(a, b);
}
