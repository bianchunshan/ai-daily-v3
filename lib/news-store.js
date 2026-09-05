const fs = require("fs/promises");
const path = require("path");

const RAW =
  "https://raw.githubusercontent.com/bianchunshan/ai-daily-v3/main/data/";
const cache = new Map();
const pending = new Map();
const TTL = 60000;

async function readData(name) {
  const previous = cache.get(name);
  if (previous && Date.now() - previous.at < TTL) return previous.value;
  if (pending.has(name)) return pending.get(name);
  const task = (async () => {
    let value,
      stale = false;
    if (process.env.AID_LOCAL_DATA === "1") {
      value = JSON.parse(
        await fs.readFile(path.join(__dirname, "..", "data", name), "utf8"),
      );
    } else {
      try {
        const response = await fetch(RAW + name, {
          signal: AbortSignal.timeout(10000),
        });
        if (!response.ok) throw new Error("News data HTTP " + response.status);
        value = await response.json();
      } catch (error) {
        stale = true;
        if (previous) value = previous.value.data;
        else
          value = JSON.parse(
            await fs.readFile(path.join(__dirname, "..", "data", name), "utf8"),
          );
      }
    }
    const result = { data: value, stale };
    if (cache.size > 40) cache.delete(cache.keys().next().value);
    cache.set(name, { at: Date.now(), value: result });
    return result;
  })().finally(() => pending.delete(name));
  pending.set(name, task);
  return task;
}

function terms(text) {
  const input = String(text || "").toLowerCase();
  const chunks = [];
  const segmenter = new Intl.Segmenter("zh-CN", { granularity: "word" });
  const stop = new Set([
    "今天",
    "最近",
    "现在",
    "什么",
    "哪些",
    "这个",
    "那个",
    "这篇",
    "新闻",
    "资讯",
    "一下",
    "如何",
    "为什么",
    "有什么",
    "有没有",
    "影响",
    "进展",
    "情况",
    "请问",
    "帮我",
    "以及",
    "还有",
    "一下子",
  ]);
  for (const part of segmenter.segment(input)) {
    if (part.isWordLike && part.segment.length >= 2 && !stop.has(part.segment))
      chunks.push(part.segment);
  }
  for (const alias of [
    "英伟达",
    "半导体",
    "脑机接口",
    "人工智能",
    "商业航天",
    "比亚迪",
    "机器人",
  ]) {
    if (input.includes(alias)) chunks.push(alias);
  }
  if (/英伟达|nvidia|\bnvda\b/.test(input))
    chunks.push("英伟达", "nvidia", "nvda");
  if (/微软|microsoft|\bmsft\b/.test(input))
    chunks.push("微软", "microsoft", "msft");
  if (/苹果|apple|\baapl\b/.test(input)) chunks.push("苹果", "apple", "aapl");
  return [...new Set(chunks)].slice(0, 30);
}

function rank(items, query) {
  const needles = terms(query);
  if (!needles.length) return [];
  return items
    .map((n) => {
      const title = String(n.title || "").toLowerCase();
      const summary = String(n.summary || "").toLowerCase();
      const labels = [
        n.category,
        ...(n.tags || []),
        ...(n.stocks || []).flatMap((s) => [s.name, s.ticker]),
      ]
        .join(" ")
        .toLowerCase();
      const score = needles.reduce(
        (score, t) =>
          score +
          (title.includes(t) ? 8 : 0) +
          (summary.includes(t) ? 3 : 0) +
          (labels.includes(t) ? 2 : 0),
        0,
      );
      return { item: n, score };
    })
    .filter((x) => x.score > 0)
    .sort(
      (a, b) =>
        b.score - a.score || Date.parse(b.item.ts) - Date.parse(a.item.ts),
    );
}

async function article(id) {
  if (!/^[a-f0-9]{16}$/.test(String(id))) return null;
  const result = await readData("articles/" + id.slice(0, 2) + ".json");
  return result.data[id] || null;
}

async function search(query, options = {}) {
  const { data } = await readData("index.json");
  let items = data.filter(
    (n) =>
      (!options.category || n.category === options.category) &&
      (!options.source || n.source === options.source) &&
      (!options.from || Date.parse(n.ts) >= Date.parse(options.from)) &&
      (!options.to || Date.parse(n.ts) < Date.parse(options.to) + 86400000),
  );
  if (query) items = rank(items, query).map((x) => x.item);
  return items;
}

module.exports = { readData, terms, rank, article, search };
