const { XMLParser } = require("fast-xml-parser");
function clean(s) {
  return String(s || "")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
async function webSearch(query, signal) {
  try {
    const r = await fetch(
      "https://www.bing.com/search?format=rss&q=" + encodeURIComponent(query),
      {
        signal: AbortSignal.any([signal, AbortSignal.timeout(8000)]),
        headers: { "User-Agent": "Mozilla/5.0" },
      },
    );
    if (!r.ok) throw new Error("Search unavailable");
    const parsed = new XMLParser({ processEntities: false }).parse(
      await r.text(),
    );
    const raw = parsed.rss?.channel?.item || [];
    return (Array.isArray(raw) ? raw : [raw])
      .slice(0, 5)
      .map((n) => ({
        title: clean(n.title),
        url: String(n.link || ""),
        summary: clean(n.description).slice(0, 700),
      }))
      .filter((n) => /^https?:\/\//.test(n.url));
  } catch (e) {
    return [];
  }
}
module.exports = { webSearch };
