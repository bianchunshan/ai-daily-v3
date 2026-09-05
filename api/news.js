const store = require("../lib/news-store");

module.exports = async function (req, res) {
  if (req.method !== "GET") return res.status(405).json({ error: "GET only" });
  const q =
    req.query ||
    Object.fromEntries(new URL(req.url, "http://local").searchParams);
  res.setHeader(
    "Cache-Control",
    "public, max-age=30, s-maxage=60, stale-while-revalidate=120",
  );
  try {
    if (q.symbols === "1") {
      const { data } = await store.readData("index.json");
      return res.status(200).json({
        symbols: [
          ...new Set(
            data
              .slice(0, 1500)
              .flatMap((n) => (n.stocks || []).map((s) => s.ticker))
              .filter(Boolean),
          ),
        ],
      });
    }
    if (q.id) {
      const item = await store.article(String(q.id));
      return res
        .status(item ? 200 : 404)
        .json(item ? { item } : { error: "未找到这条资讯" });
    }
    const [feed, status] = await Promise.all([
      store.readData("feed.json"),
      store.readData("status.json"),
    ]);
    if (q.status === "1")
      return res
        .status(200)
        .json({
          ...status.data,
          stale: status.stale,
          version: feed.data.version,
        });
    const offset = Math.max(0, Math.min(100000, parseInt(q.offset, 10) || 0));
    const limit = Math.max(1, Math.min(60, parseInt(q.limit, 10) || 40));
    let items;
    if (q.q || q.archive === "1" || q.from || q.to || q.source) {
      items = await store.search(String(q.q || "").slice(0, 200), q);
    } else {
      items = feed.data.items.filter(
        (n) => !q.category || n.category === q.category,
      );
    }
    return res.status(200).json({
      items: items.slice(offset, offset + limit),
      total: items.length,
      archiveTotal: feed.data.total,
      nextOffset: offset + limit < items.length ? offset + limit : null,
      digest: feed.data.digest,
      categories: feed.data.categories,
      sources: feed.data.sources,
      version: feed.data.version,
      status: { ...status.data, stale: status.stale || feed.stale },
    });
  } catch (error) {
    return res.status(503).json({ error: "资讯暂时无法加载，请稍后重试。" });
  }
};
