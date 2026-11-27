// POST /api/issue-status: the maintainer marks an issue open / fixed / wontfix / duplicate.
//   curl -X POST https://numpad.ahmedabdou.net/api/issue-status -H "authorization: Bearer $ADMIN_TOKEN" \
//        -d '{"signature":"0123456789ab","status":"fixed","fixed_in":"1.0.3"}'   (a crash)
//        -d '{"attachment":"<name>.png","action":"approve"|"delete"}'             (a picture; GET ?pending=1 lists the waiting ones)
//        -d '{"id":7,"status":"hidden"}'                                          (a problem report typed on the site)
// GET with the same header and ?signature=... returns the private notes of a crash's reports; ?feedback=1 returns the
// contact lines of the typed reports.
import { neon } from "@neondatabase/serverless";
import { ATTACHMENT_NAME, STATUSES, ensureTables, isAdmin, json } from "./_lib.js";

export async function handleStatus(request, sql, env) {
  if (!isAdmin(request, env)) return json({ error: "not allowed" }, 401);
  await ensureTables(sql);
  if (request.method === "GET") {
    if (new URL(request.url).searchParams.get("feedback")) {
      return json({ reports: await sql`SELECT id, created, kind, title, contact, status FROM feedback ORDER BY created DESC LIMIT 200` });
    }
    if (new URL(request.url).searchParams.get("pending")) {
      return json({ pending: await sql`SELECT a.name, a.report_id, a.mime, a.size, a.created, f.title
                                       FROM attachments a JOIN feedback f ON f.id = a.report_id WHERE NOT a.approved ORDER BY a.created LIMIT 100` });
    }
    const signature = new URL(request.url).searchParams.get("signature") || "";
    const rows = await sql`SELECT created, version, system, python, note FROM crash_reports
                           WHERE signature = ${signature} ORDER BY created DESC LIMIT 100`;
    return json({ reports: rows });
  }
  if (request.method !== "POST") return json({ error: "GET or POST only" }, 405);
  let body;
  try { body = JSON.parse(await request.text()); } catch { return json({ error: "not JSON" }, 400); }
  if (!body) return json({ error: "not JSON" }, 400);
  if (body.attachment !== undefined) {  // approve (show it) or delete a picture
    if (!ATTACHMENT_NAME.test(String(body.attachment))) return json({ error: "attachment is not valid" }, 400);
    if (body.action === "approve") {
      const done = await sql`UPDATE attachments SET approved = true WHERE name = ${body.attachment} RETURNING name`;
      return done.length ? json({ ok: true }) : json({ error: "no such picture" }, 404);
    }
    if (body.action === "delete") {
      const done = await sql`DELETE FROM attachments WHERE name = ${body.attachment} RETURNING name`;
      return done.length ? json({ ok: true }) : json({ error: "no such picture" }, 404);
    }
    return json({ error: "action must be approve or delete" }, 400);
  }
  if (!STATUSES.includes(body.status)) return json({ error: `status must be one of ${STATUSES.join(", ")}` }, 400);
  const fixedIn = typeof body.fixed_in === "string" ? body.fixed_in.slice(0, 40) : null;
  if (body.id !== undefined) {
    if (!Number.isInteger(body.id) || body.id < 1) return json({ error: "id is not valid" }, 400);
    const done = await sql`UPDATE feedback SET status = ${body.status}, fixed_in = ${fixedIn} WHERE id = ${body.id} RETURNING id`;
    return done.length ? json({ ok: true }) : json({ error: "no such report" }, 404);
  }
  if (!/^[0-9a-f]{12}$/.test(body.signature || "")) return json({ error: "signature is not valid" }, 400);
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
