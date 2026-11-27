// POST /api/crash: the app sends a crash report here, only after the user pressed Send.
import { neon } from "@neondatabase/serverless";
import { MAX_BODY, MAX_PER_HOUR, addressHash, clientAddress, ensureTables, json, validate } from "./_lib.js";

export async function handleCrash(request, sql, env) {
  if (request.method !== "POST") return json({ error: "POST only" }, 405, { allow: "POST" });
  const text = await request.text();
  if (text.length > MAX_BODY) return json({ error: "report too large" }, 413);
  let body;
  try { body = JSON.parse(text); } catch { return json({ error: "not JSON" }, 400); }
  const { report, error } = validate(body);
  if (error) return json({ error }, 400);

  await ensureTables(sql);
  const who = addressHash(clientAddress(request), env);
  const [{ n }] = await sql`SELECT count(*)::int AS n FROM crash_rate WHERE h = ${who} AND t > now() - interval '1 hour'`;
  if (n >= MAX_PER_HOUR) return json({ error: "too many reports, try again later" }, 429, { "retry-after": "3600" });
  await sql`INSERT INTO crash_rate (h) VALUES (${who})`;
  await sql`DELETE FROM crash_rate WHERE t < now() - interval '1 day'`;

  const title = `Crash: ${report.error}`.slice(0, 120);
  await sql`INSERT INTO crash_issues (signature, title, component, traceback)
            VALUES (${report.signature}, ${title}, ${report.component}, ${report.traceback})
            ON CONFLICT (signature) DO UPDATE SET count = crash_issues.count + 1, last_seen = now()`;
  await sql`INSERT INTO crash_reports (signature, version, system, python, note)
            VALUES (${report.signature}, ${report.version}, ${report.system}, ${report.python}, ${report.note})`;
  return json({ ok: true, issue: report.signature }, 201);
}

export async function POST(request) {
  if (!process.env.DATABASE_URL) return json({ error: "reports are not set up yet" }, 503);
  try {
    return await handleCrash(request, neon(process.env.DATABASE_URL), process.env);
  } catch (error) {
    console.error("crash report failed:", error);
    return json({ error: "could not save the report" }, 500);
  }
}

export function GET() { return json({ error: "POST only" }, 405, { allow: "POST" }); }
