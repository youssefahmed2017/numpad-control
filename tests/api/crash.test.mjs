import test from "node:test";
import assert from "node:assert/strict";
import { handleCrash } from "../../api/crash.js";
import { handleIssues } from "../../api/issues.js";
import { handleStatus } from "../../api/issue-status.js";
import { resetForTests, validate, addressHash, MAX_PER_HOUR } from "../../api/_lib.js";

// A fake database: remembers every query's text and values, answers like Postgres would.
function fakeSql({ rate = 0, rows = [], updated = [{ signature: "x" }] } = {}) {
  const calls = [];
  const sql = async (strings, ...values) => {
    const text = strings.join("?").replace(/\s+/g, " ").trim();
    calls.push({ text, values });
    if (text.startsWith("SELECT count(*)")) return [{ n: rate }];
    if (text.startsWith("UPDATE ")) return updated;
    if (text.startsWith("INSERT INTO feedback")) return [{ id: 7 }];
    if (text.startsWith("SELECT")) return rows;
    return [];
  };
  sql.calls = calls;
  return sql;
}

const good = () => ({
  component: "service", version: "c1eb74c", system: "Linux-7.3-x86_64", python: "3.13.1",
  error: "TimeoutExpired: notify-send timed out", traceback: "Traceback...\nTimeoutExpired", signature: "0123456789ab",
});
const post = (body, headers = {}) => new Request("https://x/api/crash", {
  method: "POST", body: typeof body === "string" ? body : JSON.stringify(body), headers: { "x-forwarded-for": "1.2.3.4", ...headers } });

test.beforeEach(resetForTests);

test("a good report is stored and counted by its signature", async () => {
  const sql = fakeSql();
  const res = await handleCrash(post(good()), sql, {});
  assert.equal(res.status, 201);
  assert.equal((await res.json()).issue, "0123456789ab");
  const texts = sql.calls.map((c) => c.text);
  assert.ok(texts.some((t) => t.startsWith("INSERT INTO crash_issues") && t.includes("ON CONFLICT (signature) DO UPDATE SET count")));
  assert.ok(texts.some((t) => t.startsWith("INSERT INTO crash_reports")));
});

test("the address is never stored, only a daily hash", async () => {
  const sql = fakeSql();
  await handleCrash(post(good()), sql, { RATE_SALT: "s" });
  assert.ok(!JSON.stringify(sql.calls).includes("1.2.3.4"));
  assert.notEqual(addressHash("1.2.3.4", {}, "2026-11-27"), addressHash("1.2.3.4", {}, "2026-11-28"));
});

test("too many reports from one address are refused", async () => {
  const res = await handleCrash(post(good()), fakeSql({ rate: MAX_PER_HOUR }), {});
  assert.equal(res.status, 429);
});

test("bad input is refused before it touches the database", async () => {
  for (const [body, status] of [["not json", 400], [[1], 400], [{ ...good(), signature: "nope" }, 400],
    [{ ...good(), component: "../etc" }, 400], [{ ...good(), error: 5 }, 400], [{ ...good(), traceback: undefined }, 400],
    ["x".repeat(30000), 413]]) {
    const sql = fakeSql();
    assert.equal((await handleCrash(post(body), sql, {})).status, status, JSON.stringify(body).slice(0, 40));
    assert.equal(sql.calls.length, 0);
  }
  assert.equal((await handleCrash(new Request("https://x/api/crash"), fakeSql(), {})).status, 405);
});

test("texts are cut, cleaned, and unknown fields are dropped", () => {
  const { report } = validate({ ...good(), traceback: "a‮b\u0000c" + "z".repeat(9000), extra: "x", note: undefined });
  assert.equal(report.traceback.length, 6000);
  assert.ok(!/[‮\u0000]/.test(report.traceback));
  assert.equal(report.extra, undefined);
  assert.equal(report.note, "");
});

test("the public list never includes notes", async () => {
  const sql = fakeSql({ rows: [{ signature: "0123456789ab", title: "Crash: x", count: 3 }] });
  const res = await handleIssues(new Request("https://x/api/issues"), sql);
  assert.equal((await res.json()).issues[0].count, 3);
  const query = sql.calls.find((c) => c.text.startsWith("SELECT i.signature")).text;
  assert.ok(!/note|system|python/.test(query));
});

test("changing a status needs the admin token", async () => {
  const env = { ADMIN_TOKEN: "t".repeat(32) };
  const req = (token, body) => new Request("https://x/api/issue-status", { method: "POST", body: JSON.stringify(body),
    headers: token ? { authorization: `Bearer ${token}` } : {} });
  const ok = { signature: "0123456789ab", status: "fixed", fixed_in: "1.0.3" };
  assert.equal((await handleStatus(req(null, ok), fakeSql(), env)).status, 401);
  assert.equal((await handleStatus(req("wrong", ok), fakeSql(), env)).status, 401);
  assert.equal((await handleStatus(req("t".repeat(32), ok), fakeSql(), {})).status, 401);          // no token configured
  assert.equal((await handleStatus(req("short", ok), fakeSql(), { ADMIN_TOKEN: "short" })).status, 401); // too weak to accept
  assert.equal((await handleStatus(req("t".repeat(32), ok), fakeSql(), env)).status, 200);
  assert.equal((await handleStatus(req("t".repeat(32), { ...ok, status: "deleted" }), fakeSql(), env)).status, 400);
  assert.equal((await handleStatus(req("t".repeat(32), ok), fakeSql({ updated: [] }), env)).status, 404);
});

// ---- problem reports typed on the website ----
import { handleReport } from "../../api/report.js";
const typed = (over = {}) => ({ kind: "bug", title: "The numpad is not detected", body: "I plugged it in and nothing happens on Fedora.",
  contact: "me@example.com", website: "", elapsed: 9000, ...over });
const send = (body) => new Request("https://x/api/report", { method: "POST", body: JSON.stringify(body), headers: { "x-forwarded-for": "5.6.7.8" } });

test("a typed report is saved, and the contact line is kept private", async () => {
  const sql = fakeSql({ rows: [{ id: 7 }] });
  sql.calls.length = 0;
  const res = await handleReport(send(typed()), sql, {});
  assert.equal(res.status, 201);
  assert.ok(sql.calls.some((c) => c.text.startsWith("INSERT INTO feedback")));
  const list = await handleIssues(new Request("https://x/api/issues"), fakeSql());
  const listQuery = fakeSql(); await handleIssues(new Request("https://x/api/issues"), listQuery);
  assert.ok(!listQuery.calls.find((c) => c.text.includes("FROM feedback") && c.text.startsWith("SELECT id, kind")).text.includes("contact"));
  assert.equal(list.status, 200);
});

test("bots (hidden field filled, or sent in under 2.5 s) get a cheerful ok and nothing is saved", async () => {
  for (const over of [{ website: "http://spam" }, { elapsed: 100 }, { elapsed: undefined }]) {
    const sql = fakeSql();
    assert.equal((await handleReport(send(typed(over)), sql, {})).status, 201);
    assert.equal(sql.calls.length, 0);
  }
});

test("typed reports are checked: kind, length, links, size, rate", async () => {
  for (const over of [{ kind: "rant" }, { title: "hi" }, { body: "short" },
    { body: "see http://a.example http://b.example http://c.example please look" }]) {
    const sql = fakeSql();
    assert.equal((await handleReport(send(typed(over)), sql, {})).status, 400, JSON.stringify(over));
    assert.equal(sql.calls.length, 0);
  }
  assert.equal((await handleReport(send(typed()), fakeSql({ rate: 3 }), {})).status, 429);
  assert.equal((await handleReport(new Request("https://x/api/report"), fakeSql(), {})).status, 405);
});

test("the maintainer can hide a typed report by id", async () => {
  const env = { ADMIN_TOKEN: "t".repeat(32) };
  const req = (body) => new Request("https://x/api/issue-status", { method: "POST", body: JSON.stringify(body), headers: { authorization: `Bearer ${"t".repeat(32)}` } });
  assert.equal((await handleStatus(req({ id: 7, status: "hidden" }), fakeSql(), env)).status, 200);
  assert.equal((await handleStatus(req({ id: "7; DROP", status: "hidden" }), fakeSql(), env)).status, 400);
  assert.equal((await handleStatus(req({ id: 7, status: "hidden" }), fakeSql({ updated: [] }), env)).status, 404);
});
