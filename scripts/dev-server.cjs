const http = require("http");
const fs = require("fs/promises");
const path = require("path");
const root = path.join(__dirname, "..");
process.env.AID_LOCAL_DATA = "1";
const handlers = Object.fromEntries(
  ["news", "chat", "quote", "image"].map((n) => [n, require("../api/" + n)]),
);
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
};
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  res.status = function (code) {
    res.statusCode = code;
    return res;
  };
  res.json = function (data) {
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify(data));
  };
  res.send = function (data) {
    res.end(data);
  };
  try {
    if (url.pathname.startsWith("/api/")) {
      const handler = handlers[url.pathname.slice(5)];
      if (!handler) return res.status(404).end();
      req.query = Object.fromEntries(url.searchParams);
      let bytes = 0,
        chunks = [];
      for await (const chunk of req) {
        bytes += chunk.length;
        if (bytes > 24000) return res.status(413).json({ error: "too large" });
        chunks.push(chunk);
      }
      if (bytes) {
        try {
          req.body = JSON.parse(Buffer.concat(chunks).toString());
        } catch {
          return res.status(400).json({ error: "invalid JSON" });
        }
      }
      await handler(req, res);
      return;
    }
    const name =
      url.pathname === "/"
        ? "index.html"
        : decodeURIComponent(url.pathname.slice(1));
    const file = path.resolve(root, name);
    if (
      !file.startsWith(root + path.sep) ||
      name.startsWith(".") ||
      ![".html", ".css", ".js", ".svg", ".json"].includes(path.extname(file))
    )
      return res.status(404).end();
    res.setHeader("Content-Type", types[path.extname(file)]);
    res.end(await fs.readFile(file));
  } catch (e) {
    if (!res.headersSent)
      res.status(500).json({ error: "Local request failed" });
    else res.end();
  }
});
server.listen(Number(process.env.PORT || 4187), "127.0.0.1", () =>
  console.log(
    "AI Daily dev server http://127.0.0.1:" + (process.env.PORT || 4187),
  ),
);
