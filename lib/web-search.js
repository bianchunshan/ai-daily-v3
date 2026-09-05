const { XMLParser } = require("fast-xml-parser");
const cheerio = require("cheerio");
const { terms } = require("./news-store");
function clean(s) {
  return cheerio.load(String(s || "")).text()
    .replace(/\s+/g, " ")
    .trim();
}

function relevant(results, query) {
  const sites = [...query.matchAll(/\bsite:([\w.-]+)/gi)].map(m => m[1].toLowerCase());
  const generic = new Set(["官方", "文档", "搜索", "检索", "联网", "最新", "进展", "official", "documentation", "docs", "news", "latest", "the", "and"]);
  const needles = terms(query.replace(/\bsite:[\w.-]+/gi, "")).filter(t => !generic.has(t));
  return results.filter(n => {
    let url;
    try { url = new URL(n.url); } catch { return false; }
    if (!["http:", "https:"].includes(url.protocol)) return false;
    if (sites.length && !sites.some(s => url.hostname === s || url.hostname.endsWith("." + s))) return false;
    const text = [n.title, n.summary, n.url].join(" ").toLowerCase();
    return needles.length ? needles.some(t => text.includes(t)) : sites.length > 0;
  }).slice(0, 5);
}

async function duckSearch(query, signal) {
  const r = await fetch("https://html.duckduckgo.com/html/?q=" + encodeURIComponent(query), {
    signal, headers: { "User-Agent": "Mozilla/5.0" },
  });
  if (!r.ok) return [];
  const $ = cheerio.load(await r.text());
  return $(".result__body").toArray().slice(0, 10).map(el => {
    const a = $(el).find(".result__a");
    const href = a.attr("href") || "";
    let url = "";
    if (href) {
      try {
        const target = new URL(href, "https://duckduckgo.com");
        url = target.searchParams.get("uddg") || target.href;
      } catch {}
    }
    return { title: a.text().trim(), url, summary: $(el).find(".result__snippet").text().trim().slice(0, 700) };
  });
}

async function webSearch(query, signal) {
  const timeout = () => AbortSignal.any([...(signal ? [signal] : []), AbortSignal.timeout(8000)]);
  const key = process.env.KIMI_WEB_SEARCH_API_KEY || process.env.KIMI_KEY;
  if (key) {
    try {
      const response = await fetch("https://api.kimi.com/coding/v1/search", {
        method: "POST",
        signal: AbortSignal.any([...(signal ? [signal] : []), AbortSignal.timeout(15000)]),
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + key, "User-Agent": "AI-Daily/1.0" },
        body: JSON.stringify({ text_query: query, limit: 5, enable_page_crawling: false, timeout_seconds: 12 }),
      });
      if (response.ok) {
        const data = await response.json();
        const results = relevant((data.search_results || []).map(n => ({
          title: n.title, url: n.url, source: n.site_name, date: n.date,
          summary: clean(n.snippet || n.content).slice(0, 900),
        })), query);
        if (results.length) return results;
      }
    } catch {}
  }
  if (signal?.aborted) return [];
  try {
    const results = relevant(await duckSearch(query, timeout()), query);
    if (results.length) return results;
  } catch {}
  if (signal?.aborted) return [];
  try {
    const r = await fetch(
      "https://www.bing.com/search?format=rss&q=" + encodeURIComponent(query),
      {
        signal: timeout(),
        headers: { "User-Agent": "Mozilla/5.0" },
      },
    );
    if (!r.ok) throw new Error("Search unavailable");
    const parsed = new XMLParser({ processEntities: false }).parse(
      await r.text(),
    );
    const raw = parsed.rss?.channel?.item || [];
    return relevant((Array.isArray(raw) ? raw : [raw])
      .slice(0, 10)
      .map((n) => ({
        title: clean(n.title),
        url: String(n.link || ""),
        summary: clean(n.description).slice(0, 700),
      }))
      .filter((n) => /^https?:\/\//.test(n.url)), query);
  } catch (e) {
    return [];
  }
}
module.exports = { webSearch, relevant };
