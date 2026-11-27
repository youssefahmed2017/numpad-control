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
    if (text.startsWith("UPDATE crash_issues")) return updated;
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
