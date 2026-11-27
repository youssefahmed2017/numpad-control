// POST /api/report-status: the person who wrote a report closes or reopens it, with the key their browser was given.
//   {"id": 7, "token": "...", "status": "closed" | "open"}
// Only open <-> closed: a report the maintainer marked fixed / won't fix / duplicate / hidden stays as set.
import { neon } from "@neondatabase/serverless";
import { MAX_BODY, OWNER_STATUSES, ensureTables, hashToken, json, sameSecret } from "./_lib.js";

export async function handleReportStatus(request, sql) {
  if (request.method !== "POST") return json({ error: "POST only" }, 405, { allow: "POST" });
  const text = await request.text();
  if (text.length > MAX_BODY) return json({ error: "too large" }, 413);
  let body;
  try { body = JSON.parse(text); } catch { return json({ error: "not JSON" }, 400); }
  if (!body || !Number.isInteger(Number(body.id)) || Number(body.id) < 1 || typeof body.token !== "string") return json({ error: "id and token are needed" }, 400);
  if (!OWNER_STATUSES.includes(body.status)) return json({ error: "status must be open or closed" }, 400);
  await ensureTables(sql);
  const [row] = await sql`SELECT status, manage_hash FROM feedback WHERE id = ${Number(body.id)}`;
  // The same answer for "no such report" and "wrong key", so ids can't be probed.
  if (!row || !row.manage_hash || !sameSecret(hashToken(body.token), row.manage_hash)) return json({ error: "not allowed" }, 403);
  if (!OWNER_STATUSES.includes(row.status)) return json({ error: "the maintainer has settled this one" }, 409);
  await sql`UPDATE feedback SET status = ${body.status} WHERE id = ${Number(body.id)}`;
  return json({ ok: true, status: body.status });
}

export async function POST(request) {
  if (!process.env.DATABASE_URL) return json({ error: "reports are not set up yet" }, 503);
  try {
    return await handleReportStatus(request, neon(process.env.DATABASE_URL));
  } catch (error) {
    console.error("report-status failed:", error);
    return json({ error: "failed" }, 500);
  }
}

export function GET() { return json({ error: "POST only" }, 405, { allow: "POST" }); }
