// Only permit images stored on an article; this endpoint cannot proxy arbitrary URLs.
const { article } = require("../lib/news-store");
const ALLOWED = new Set([
  "img.ithome.com",
  "cdn.mos.cms.futurecdn.net",
  "media.wired.com",
  "techcrunch.com",
  "www.therobotreport.com",
  "i0.wp.com",
  "i1.wp.com",
  "i2.wp.com",
]);
module.exports = async function (req, res) {
  if (req.method !== "GET") return res.status(405).end();
  try {
    const item = await article(String(req.query?.id || ""));
    const url = new URL(item?.image || "");
    if (
      url.protocol !== "https:" ||
      !ALLOWED.has(url.hostname) ||
      url.username ||
      url.password
    )
      return res.status(404).end();
    const upstream = await fetch(url, {
      redirect: "error",
      signal: AbortSignal.timeout(8000),
      headers: { "User-Agent": "Mozilla/5.0", Referer: url.origin + "/" },
    });
    const type = upstream.headers.get("content-type") || "";
    if (!upstream.ok || !/^image\/(jpeg|png|webp|gif|avif)(;|$)/.test(type))
      return res.status(404).end();
    const reader = upstream.body.getReader();
    const chunks = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > 4 * 1024 * 1024) {
        await reader.cancel();
        return res.status(413).end();
      }
      chunks.push(Buffer.from(value));
    }
    res.setHeader("Content-Type", type);
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Cache-Control", "public, max-age=86400, s-maxage=604800");
    return res.status(200).send(Buffer.concat(chunks));
  } catch (e) {
    return res.status(404).end();
  }
};
