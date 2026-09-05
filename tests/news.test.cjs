const test = require("node:test");
const assert = require("node:assert/strict");
const { terms, rank } = require("../lib/news-store");
test("Chinese question retrieves entity instead of newest unrelated article", () => {
  const items = [
    {
      id: "headphones",
      title: "无线耳机首销",
      summary: "蓝牙音频产品",
      ts: "2026-09-05",
    },
    {
      id: "nvda",
      title: "英伟达发布新模型",
      summary: "推理优化",
      ts: "2026-09-04",
    },
  ];
  assert(terms("英伟达最近有什么进展").includes("英伟达"));
  assert.equal(rank(items, "英伟达最近有什么进展")[0].item.id, "nvda");
  assert.deepEqual(rank(items, "质子衰变"), []);
});
test("Aliases retrieve English company references", () => {
  assert.equal(
    rank(
      [{ title: "NVIDIA introduces new inference technology" }],
      "英伟达最新进展",
    )[0].score > 0,
    true,
  );
});
test("Article ids cannot escape data directory", async () => {
  assert.equal(await require("../lib/news-store").article("../../auth"), null);
});
