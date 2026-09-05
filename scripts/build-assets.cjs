const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..");
const vendor = path.join(root, "assets/vendor");
fs.mkdirSync(vendor, { recursive: true });
for (const [source, name] of [
  ["marked/lib/marked.umd.js", "marked.js"],
  ["dompurify/dist/purify.min.js", "purify.js"],
])
  fs.copyFileSync(
    path.join(root, "node_modules", source),
    path.join(vendor, name),
  );
fs.mkdirSync(path.join(root, "assets/icons"), { recursive: true });
for (const name of [
  "search",
  "sun-moon",
  "newspaper",
  "chart-no-axes-combined",
  "message-circle",
  "arrow-left",
  "arrow-up",
  "x",
  "square",
  "rotate-ccw",
  "refresh-cw",
  "bookmark",
  "share-2",
  "chevron-down",
])
  fs.copyFileSync(
    path.join(root, "node_modules/lucide-static/icons", name + ".svg"),
    path.join(root, "assets/icons", name + ".svg"),
  );

const output = path.join(root, "public");
for (const name of ["marked", "dompurify", "lucide-static"]) {
  fs.copyFileSync(
    path.join(root, "node_modules", name, "LICENSE"),
    path.join(vendor, name + ".LICENSE"),
  );
}
fs.mkdirSync(output, { recursive: true });
for (const name of ["index.html", "detail.html", "stock.html"]) {
  fs.copyFileSync(path.join(root, name), path.join(output, name));
}
fs.cpSync(path.join(root, "assets"), path.join(output, "assets"), { recursive: true });
