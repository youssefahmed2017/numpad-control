// GET /api/issues: the public list behind the Issues page. Notes and system details stay private.
import { neon } from "@neondatabase/serverless";
import { ensureTables, json } from "./_lib.js";

export async function handleIssues(request, sql) {
  await ensureTables(sql);
  const rows = await sql`
    SELECT i.signature, i.title, i.component, i.status, i.fixed_in, i.count, i.first_seen, i.last_seen, i.traceback,
           coalesce((SELECT array_agg(DISTINCT version) FROM crash_reports r WHERE r.signature = i.signature), '{}') AS versions
    FROM crash_issues i ORDER BY (i.status = 'open') DESC, i.last_seen DESC LIMIT 200`;
  return json({ issues: rows }, 200, { "cache-control": "public, s-maxage=60, stale-while-revalidate=300" });
}

export async function GET(request) {
  if (!process.env.DATABASE_URL) return json({ issues: [] }, 200, { "cache-control": "no-store" });
  try {
    return await handleIssues(request, neon(process.env.DATABASE_URL));
  } catch (error) {
    console.error("issues failed:", error);
    return json({ error: "could not read the issues" }, 500);
  }
}
