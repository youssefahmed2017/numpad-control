// /issues-attachments/<hash>.png (rewritten here by vercel.json): GET shows an approved picture; POST uploads one.
//   POST /api/attachment   headers: x-report-id, x-manage-token (the key the browser got with the report); body: the file itself.
// A new picture is hidden (404) until the maintainer approves it; the maintainer's token can look at pending ones.
import { neon } from "@neondatabase/serverless";
import {
  ATTACHMENT_NAME, MAX_DAILY_BYTES, MAX_FILE, MAX_FILES_PER_REPORT, MAX_PENDING, MAX_STORED_BYTES, addressHash, clientAddress,
  ensureTables, hashToken, isAdmin, json, newAttachmentName, sameSecret, sniff,
} from "./_lib.js";

const SERVE_HEADERS = {
  "x-content-type-options": "nosniff",
  "content-security-policy": "default-src 'none'; sandbox",
  "cross-origin-resource-policy": "same-origin",
  "referrer-policy": "no-referrer",
};

export async function handleServe(request, sql, env) {
  const name = new URL(request.url).searchParams.get("name") || "";
  if (!ATTACHMENT_NAME.test(name)) return new Response("Not found", { status: 404 });
  await ensureTables(sql);
  const [row] = await sql`SELECT a.mime, a.approved, f.status, encode(a.data, 'base64') AS b64
                          FROM attachments a JOIN feedback f ON f.id = a.report_id WHERE a.name = ${name}`;
  const maintainer = isAdmin(request, env);
  if (!row || (!maintainer && (!row.approved || row.status === "hidden"))) return new Response("Not found", { status: 404 });
  const cache = row.approved && row.status !== "hidden" ? "public, max-age=31536000, immutable" : "no-store";
  return new Response(Buffer.from(row.b64, "base64"), { status: 200, headers: { ...SERVE_HEADERS, "content-type": row.mime, "cache-control": cache } });
}

export async function handleUpload(request, sql, env) {
  const id = Number(request.headers.get("x-report-id"));
  const token = request.headers.get("x-manage-token") || "";
  if (!Number.isInteger(id) || id < 1 || !token) return json({ error: "report id and key are needed" }, 400);
  if (Number(request.headers.get("content-length") || 0) > MAX_FILE + 1000) return json({ error: "that picture is over 4 MB" }, 413);
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.length > MAX_FILE) return json({ error: "that picture is over 4 MB" }, 413);
  const kind = sniff(bytes);
  if (!kind) return json({ error: "only PNG, JPG, GIF and WEBP pictures are accepted" }, 415);

  await ensureTables(sql);
  const [report] = await sql`SELECT status, manage_hash FROM feedback WHERE id = ${id}`;
  if (!report || !report.manage_hash || !sameSecret(hashToken(token), report.manage_hash) || report.status === "hidden") return json({ error: "not allowed" }, 403);

  const who = "a:" + addressHash(clientAddress(request), env);
  const [{ mine, pending, stored, today }] = await sql`
    SELECT (SELECT count(*)::int FROM attachments WHERE report_id = ${id}) AS mine,
           (SELECT count(*)::int FROM attachments WHERE NOT approved) AS pending,
           (SELECT coalesce(sum(size), 0)::bigint FROM attachments) AS stored,
           (SELECT coalesce(sum(size), 0)::bigint FROM attachments WHERE h = ${who} AND created > now() - interval '1 day') AS today`;
  if (mine >= MAX_FILES_PER_REPORT) return json({ error: `at most ${MAX_FILES_PER_REPORT} pictures per report` }, 409);
  if (Number(today) + bytes.length > MAX_DAILY_BYTES) return json({ error: "that is a lot of pictures for one day: please try again tomorrow" }, 429);
  if (pending >= MAX_PENDING || Number(stored) + bytes.length > MAX_STORED_BYTES) return json({ error: "pictures can't be accepted right now" }, 503);

  const name = newAttachmentName(kind.ext);
  await sql`INSERT INTO attachments (report_id, name, mime, size, data, h)
            VALUES (${id}, ${name}, ${kind.mime}, ${bytes.length}, decode(${Buffer.from(bytes).toString("base64")}, 'base64'), ${who})`;
  return json({ ok: true, name, pending: true }, 201);
}

export async function GET(request) {
  if (!process.env.DATABASE_URL) return new Response("Not found", { status: 404 });
  try { return await handleServe(request, neon(process.env.DATABASE_URL), process.env); }
  catch (error) { console.error("attachment failed:", error); return new Response("Error", { status: 500 }); }
}

export async function POST(request) {
  if (!process.env.DATABASE_URL) return json({ error: "reports are not set up yet" }, 503);
  try { return await handleUpload(request, neon(process.env.DATABASE_URL), process.env); }
  catch (error) { console.error("upload failed:", error); return json({ error: "could not save the picture" }, 500); }
}
