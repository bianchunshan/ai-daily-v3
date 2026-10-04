const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const { filterItems, dateStart } = require("../lib/news-store");

test("date range uses inclusive Beijing days, not UTC days", () => {
  const data = [
    { id: "before", ts: "2026-10-02T15:59:59Z" },
    { id: "start", ts: "2026-10-02T16:00:00Z" },
    { id: "end", ts: "2026-10-03T15:59:59Z" },
    { id: "after", ts: "2026-10-03T16:00:00Z" },
  ];
  assert.deepEqual(filterItems(data, "", { from: "2026-10-03", to: "2026-10-03" }).map(n => n.id), ["start", "end"]);
  assert.equal(filterItems(data, "", { from: "2026-10-03" }).length, 3);
  assert.equal(filterItems(data, "", { to: "2026-10-03" }).length, 3);
  assert.equal(filterItems(data, "").length, 4);
});

test("invalid and inverted dates cannot silently produce an empty feed", () => {
  for (const value of ["2026-02-30", "2026-13-01", "bad", "2026-1-1"])
    assert.throws(() => dateStart(value), RangeError);
  assert.throws(() => filterItems([], "", { from: "2026-10-04", to: "2026-10-03" }), RangeError);
  assert.equal(dateStart("2024-02-29"), Date.parse("2024-02-28T16:00:00Z"));
});

test("status distinguishes healthy, degraded, failed, and stalled updates", () => {
  const context = { window: {}, Date, Map };
  vm.runInNewContext(fs.readFileSync(require.resolve("../assets/app.js"), "utf8"), context);
  const health = context.window.AID.updateHealth;
  const now = Date.parse("2026-10-04T13:00:00Z");
  const ok = { checkedAt: "2026-10-04T12:55:00Z", state: "ok", sources: [{ ok: true }] };
  assert.equal(health(ok, now).state, "ok");
  for (const change of [{ pendingRetries: 1 }, { exhaustedRetries: 15 }, { sources: [{ ok: false }] }, { stale: true }, { state: "partial" }])
    assert.equal(health({ ...ok, ...change }, now).state, "partial");
  assert.equal(health({ ...ok, state: "error" }, now).state, "error");
  assert.equal(health({ ...ok, checkedAt: "2026-10-04T12:30:00Z" }, now).state, "stalled");
  assert.equal(health({}, now).state, "stalled");
  assert.match(context.window.AID.dateLabel("2026-10-03T16:01:00Z"), /10\/04.*00:01/);
});

test("archive API paginates beyond the recent feed and keeps category totals", async (t) => {
  const store = require("../lib/news-store");
  const all = Array.from({ length: 114 }, (_, i) => ({ id: String(i), category: "量子科技" }));
  const feed = { items: all.slice(0, 2), total: 200, categories: { 量子科技: 114 }, sources: {}, version: "test" };
  t.mock.method(store, "readData", async name => ({ data: name === "feed.json" ? feed : { state: "ok" } }));
  t.mock.method(store, "search", async (_, options) => all.filter(n => n.category === options.category));
  const handler = require("../api/news");
  async function request(query) {
    let response;
    await handler({ method: "GET", query }, { setHeader() {}, status(code) { assert.equal(code, 200); return this; }, json(value) { response = value; } });
    return response;
  }
  const recent = await request({ category: "量子科技" });
  assert.equal(recent.total, 2);
  assert.equal(recent.categoryTotal, 114);
  const archived = await request({ category: "量子科技", archive: "1", offset: "40", limit: "40" });
  assert.equal(archived.scope, "archive");
  assert.equal(archived.total, 114);
  assert.equal(archived.items[0].id, "40");
  assert.equal(archived.nextOffset, 80);
});
