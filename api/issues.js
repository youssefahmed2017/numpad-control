// GET /api/issues: the public lists behind the Issues page. Notes, contacts and system details stay private.
import { neon } from "@neondatabase/serverless";
import { ensureTables, isAdmin, json } from "./_lib.js";

export async function handleIssues(request, sql, env = {}) {
  await ensureTables(sql);
  const all = isAdmin(request, env);  // the maintainer also sees hidden items, and never a cached copy
  const rows = await sql`
    SELECT i.signature, i.title, i.component, i.status, i.fixed_in, i.count, i.first_seen, i.last_seen, i.traceback,
           coalesce((SELECT array_agg(DISTINCT version) FROM crash_reports r WHERE r.signature = i.signature), '{}') AS versions
    FROM crash_issues i WHERE (${all} OR i.status <> 'hidden') ORDER BY (i.status = 'open') DESC, i.last_seen DESC LIMIT 200`;
  const reports = await sql`SELECT f.id, f.kind, f.title, f.body, f.status, f.fixed_in, f.created,
           coalesce((SELECT json_agg(a.name ORDER BY a.id) FROM attachments a WHERE a.report_id = f.id AND a.approved), '[]'::json) AS files,
           (SELECT count(*)::int FROM attachments a WHERE a.report_id = f.id AND NOT a.approved) AS pending_files
    FROM feedback f WHERE (${all} OR f.status <> 'hidden') ORDER BY (f.status = 'open') DESC, f.created DESC LIMIT 200`;
  return json({ issues: rows, reports }, 200,
              { "cache-control": all ? "no-store" : "public, s-maxage=60, stale-while-revalidate=300" });
}

export async function GET(request) {
  if (!process.env.DATABASE_URL) return json({ issues: [], reports: [] }, 200, { "cache-control": "no-store" });
  try {
    return await handleIssues(request, neon(process.env.DATABASE_URL), process.env);
  } catch (error) {
    console.error("issues failed:", error);
    return json({ error: "could not read the issues" }, 500);
  }
}
