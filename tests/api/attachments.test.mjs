import test from "node:test";
import assert from "node:assert/strict";
import { handleServe, handleUpload } from "../../api/attachment.js";
import { handleStatus } from "../../api/issue-status.js";
import { resetForTests, sniff, hashToken, MAX_FILE, MAX_FILES_PER_REPORT, MAX_PENDING } from "../../api/_lib.js";

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 73, 72, 68, 82]);
const JPG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 16, 74, 70, 73, 70, 0, 1, 1]);
const GIF = new Uint8Array([...Buffer.from("GIF89a"), 1, 0, 1, 0, 0, 0, 0]);
const WEBP = new Uint8Array([...Buffer.from("RIFF"), 1, 0, 0, 0, ...Buffer.from("WEBPVP8 ")]);
const EXE = new Uint8Array([0x4d, 0x5a, 0x90, 0, 3, 0, 0, 0, 4, 0, 0, 0, 0xff, 0xff]);
const SVG = new Uint8Array(Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'));
const MP4 = new Uint8Array([0, 0, 0, 24, ...Buffer.from("ftypisom"), 0, 0, 2, 0, ...Buffer.from("isom")]);

const KEY = "owner-key";
function fakeSql({ report = { status: "open", manage_hash: hashToken(KEY) }, counts = { mine: 0, pending: 0, stored: 0, today: 0 }, row } = {}) {
  const calls = [];
  const sql = async (strings, ...values) => {
    const text = strings.join("?").replace(/\s+/g, " ").trim();
    calls.push({ text, values });
    if (text.startsWith("SELECT status, manage_hash")) return report ? [report] : [];
    if (text.startsWith("SELECT (SELECT count")) return [counts];
    if (text.startsWith("SELECT a.mime")) return row ? [row] : [];
    if (text.startsWith("UPDATE attachments") || text.startsWith("DELETE FROM attachments")) return [{ name: "x" }];
    return [];
  };
  sql.calls = calls;
  return sql;
}
const upload = (bytes, headers = {}) => new Request("https://x/api/attachment", {
  method: "POST", body: bytes, headers: { "x-report-id": "7", "x-manage-token": KEY, "x-forwarded-for": "9.9.9.9", ...headers } });
const serve = (name, headers = {}) => new Request(`https://x/issues-attachments/${name}?name=${name}`, { headers });
const NAME = "0123456789abcdef0123456789abcdef.png";

test.beforeEach(resetForTests);

test("pictures are recognised by their first bytes, nothing else is", () => {
  assert.deepEqual([PNG, JPG, GIF, WEBP].map((b) => sniff(b).ext), ["png", "jpg", "gif", "webp"]);
  for (const bad of [EXE, SVG, MP4, new Uint8Array(0), new Uint8Array(5)]) assert.equal(sniff(bad), null);
});

test("an upload is stored hidden, under a random name, and the address is not stored", async () => {
  const sql = fakeSql();
  const res = await handleUpload(upload(PNG, { "content-type": "text/html" }), sql, {});   // the declared type is ignored
  assert.equal(res.status, 201);
  const { name } = await res.json();
  assert.match(name, /^[0-9a-f]{32}\.png$/);
  const insert = sql.calls.find((c) => c.text.startsWith("INSERT INTO attachments"));
  assert.ok(insert.values.includes("image/png"));
  assert.ok(!JSON.stringify(sql.calls).includes("9.9.9.9"));
  assert.ok(/approved/.test(sql.calls[0].text) === false);  // never inserted as approved: the column's default is false
});

test("not a picture, too big, wrong key, hidden or full: all refused before anything is stored", async () => {
  const cases = [
    [upload(EXE), fakeSql(), 415], [upload(SVG), fakeSql(), 415], [upload(MP4), fakeSql(), 415],
    [upload(new Uint8Array(MAX_FILE + 1).fill(1)), fakeSql(), 413],
    [upload(PNG, { "x-manage-token": "wrong" }), fakeSql(), 403],
    [upload(PNG), fakeSql({ report: null }), 403],
    [upload(PNG), fakeSql({ report: { status: "hidden", manage_hash: hashToken(KEY) } }), 403],
    [upload(PNG, { "x-report-id": "abc" }), fakeSql(), 400],
    [upload(PNG), fakeSql({ counts: { mine: MAX_FILES_PER_REPORT, pending: 0, stored: 0, today: 0 } }), 409],
    [upload(PNG), fakeSql({ counts: { mine: 0, pending: 0, stored: 0, today: 20_000_000 } }), 429],
    [upload(PNG), fakeSql({ counts: { mine: 0, pending: MAX_PENDING, stored: 0, today: 0 } }), 503],
    [upload(PNG), fakeSql({ counts: { mine: 0, pending: 0, stored: 300_000_000, today: 0 } }), 503],
  ];
  for (const [req, sql, status] of cases) {
    resetForTests();
    assert.equal((await handleUpload(req, sql, {})).status, status);
    assert.ok(!sql.calls.some((c) => c.text.startsWith("INSERT")));
  }
});

test("only approved pictures of visible reports are served, with safe headers", async () => {
  const b64 = Buffer.from(PNG).toString("base64");
  const env = { ADMIN_TOKEN: "t".repeat(32) };
  const approved = { mime: "image/png", approved: true, status: "open", b64 };
  const ok = await handleServe(serve(NAME), fakeSql({ row: approved }), env);
  assert.equal(ok.status, 200);
  assert.equal(ok.headers.get("content-type"), "image/png");
  assert.equal(ok.headers.get("x-content-type-options"), "nosniff");
  assert.match(ok.headers.get("content-security-policy"), /sandbox/);
  assert.match(ok.headers.get("cache-control"), /immutable/);
  assert.deepEqual(new Uint8Array(await ok.arrayBuffer()), PNG);
  for (const row of [{ ...approved, approved: false }, { ...approved, status: "hidden" }, undefined])
    assert.equal((await handleServe(serve(NAME), fakeSql({ row }), env)).status, 404);
  const admin = await handleServe(serve(NAME, { authorization: `Bearer ${"t".repeat(32)}` }), fakeSql({ row: { ...approved, approved: false } }), env);
  assert.equal(admin.status, 200);
  assert.equal(admin.headers.get("cache-control"), "no-store");
  for (const bad of ["../etc/passwd", "x.png", "0123456789abcdef0123456789abcdef.svg", "0123456789ABCDEF0123456789ABCDEF.png"])
    assert.equal((await handleServe(serve(bad), fakeSql({ row: approved }), env)).status, 404);
});

test("the maintainer approves, deletes and lists waiting pictures", async () => {
  const env = { ADMIN_TOKEN: "t".repeat(32) };
  const auth = { authorization: `Bearer ${"t".repeat(32)}` };
  const post = (body, headers = auth) => new Request("https://x/api/issue-status", { method: "POST", body: JSON.stringify(body), headers });
  assert.equal((await handleStatus(post({ attachment: NAME, action: "approve" }), fakeSql(), env)).status, 200);
  assert.equal((await handleStatus(post({ attachment: NAME, action: "delete" }), fakeSql(), env)).status, 200);
  assert.equal((await handleStatus(post({ attachment: NAME, action: "burn" }), fakeSql(), env)).status, 400);
  assert.equal((await handleStatus(post({ attachment: "../x", action: "approve" }), fakeSql(), env)).status, 400);
  assert.equal((await handleStatus(post({ attachment: NAME, action: "approve" }, {}), fakeSql(), env)).status, 401);
  const list = await handleStatus(new Request("https://x/api/issue-status?pending=1", { headers: auth }), fakeSql(), env);
  assert.equal(list.status, 200);
});
