// POST /api/report: a problem or idea typed on the website's Issues page. No account needed.
import { neon } from "@neondatabase/serverless";
import { MAX_BODY, MAX_FEEDBACK_PER_HOUR, addressHash, clientAddress, ensureTables, json, validateFeedback } from "./_lib.js";

export async function handleReport(request, sql, env) {
  if (request.method !== "POST") return json({ error: "POST only" }, 405, { allow: "POST" });
  const text = await request.text();
  if (text.length > MAX_BODY) return json({ error: "too large" }, 413);
  let body;
  try { body = JSON.parse(text); } catch { return json({ error: "not JSON" }, 400); }
  const { feedback, ignore, error } = validateFeedback(body);
  if (error) return json({ error }, 400);
  if (ignore) return json({ ok: true }, 201);  // a bot: look pleased, save nothing

  await ensureTables(sql);
  const who = "f:" + addressHash(clientAddress(request), env);
  const [{ n }] = await sql`SELECT count(*)::int AS n FROM crash_rate WHERE h = ${who} AND t > now() - interval '1 hour'`;
  if (n >= MAX_FEEDBACK_PER_HOUR) return json({ error: "that is a lot of reports: please try again in an hour" }, 429, { "retry-after": "3600" });
  await sql`INSERT INTO crash_rate (h) VALUES (${who})`;
  const [row] = await sql`INSERT INTO feedback (kind, title, body, contact) VALUES (${feedback.kind}, ${feedback.title}, ${feedback.body}, ${feedback.contact})
                          RETURNING id`;
  return json({ ok: true, id: row?.id ?? null }, 201);
}

export async function POST(request) {
  if (!process.env.DATABASE_URL) return json({ error: "reports are not set up yet" }, 503);
  try {
    return await handleReport(request, neon(process.env.DATABASE_URL), process.env);
  } catch (error) {
    console.error("report failed:", error);
    return json({ error: "could not save the report" }, 500);
  }
}

export function GET() { return json({ error: "POST only" }, 405, { allow: "POST" }); }
