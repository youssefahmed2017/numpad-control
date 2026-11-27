// POST /api/issue-status: the maintainer marks an issue open / fixed / wontfix / duplicate.
//   curl -X POST https://numpad.ahmedabdou.net/api/issue-status -H "authorization: Bearer $ADMIN_TOKEN" \
//        -d '{"signature":"0123456789ab","status":"fixed","fixed_in":"1.0.3"}'
// GET with the same header and ?signature=... returns the private notes of that issue's reports.
import { neon } from "@neondatabase/serverless";
import { STATUSES, ensureTables, json, sameSecret } from "./_lib.js";

function authorised(request, env) {
  const given = (request.headers.get("authorization") || "").replace(/^Bearer /i, "");
  return Boolean(env.ADMIN_TOKEN) && env.ADMIN_TOKEN.length >= 24 && sameSecret(given, env.ADMIN_TOKEN);
}

export async function handleStatus(request, sql, env) {
  if (!authorised(request, env)) return json({ error: "not allowed" }, 401);
  await ensureTables(sql);
  if (request.method === "GET") {
    const signature = new URL(request.url).searchParams.get("signature") || "";
    const rows = await sql`SELECT created, version, system, python, note FROM crash_reports
                           WHERE signature = ${signature} ORDER BY created DESC LIMIT 100`;
    return json({ reports: rows });
  }
  if (request.method !== "POST") return json({ error: "GET or POST only" }, 405);
  let body;
  try { body = JSON.parse(await request.text()); } catch { return json({ error: "not JSON" }, 400); }
  if (!body || !/^[0-9a-f]{12}$/.test(body.signature || "")) return json({ error: "signature is not valid" }, 400);
  if (!STATUSES.includes(body.status)) return json({ error: `status must be one of ${STATUSES.join(", ")}` }, 400);
  const fixedIn = typeof body.fixed_in === "string" ? body.fixed_in.slice(0, 40) : null;
  const done = await sql`UPDATE crash_issues SET status = ${body.status}, fixed_in = ${fixedIn}
                         WHERE signature = ${body.signature} RETURNING signature`;
  return done.length ? json({ ok: true }) : json({ error: "no such issue" }, 404);
}

async function run(request) {
  if (!process.env.DATABASE_URL) return json({ error: "reports are not set up yet" }, 503);
  try {
    return await handleStatus(request, neon(process.env.DATABASE_URL), process.env);
  } catch (error) {
    console.error("status failed:", error);
    return json({ error: "failed" }, 500);
  }
}
export const GET = run;
export const POST = run;
