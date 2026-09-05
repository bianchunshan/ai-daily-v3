const {
  chromium,
} = require("/Users/steve/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const fs = require("fs");
const path = require("path");
const assert = require("node:assert/strict");
const base = process.env.TEST_BASE || "http://127.0.0.1:4187";
const out = path.resolve(".test-output");
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const results = { base, checks: [], errors: [], failed: [] };
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      colorScheme: "light",
    });
    page.on("pageerror", (e) => results.errors.push(e.message));
    page.on("requestfailed", (r) =>
      results.failed.push({ url: r.url(), error: r.failure()?.errorText }),
    );
    await page.goto(base);
    await page.locator(".item-title").first().waitFor();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: path.join(out, "desktop.png") });
    assert.equal(await page.locator(".item").count(), 40);
    results.checks.push("40 items on initial page");
    await page.locator("#more").click();
    await page.waitForFunction(
      () => document.querySelectorAll(".item").length === 80,
    );
    results.checks.push("pagination appends 40");
    await page.locator("#searchBtn").click();
    await page
      .locator("#searchInput")
      .fill("英伟达NVIDIA App将支持Resizable BAR");
    await page.waitForTimeout(500);
    await page.waitForLoadState("networkidle");
    assert((await page.locator("#feed").innerText()).includes("Resizable BAR"));
    results.checks.push("full archive title searchable");
    await page.locator("#searchClear").click();
    await page.locator(".item-title").first().waitFor();
    await page.waitForLoadState("networkidle");
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: width === 320 ? 568 : 844 });
      const dim = await page.evaluate(() => ({
        width: innerWidth,
        scroll: document.documentElement.scrollWidth,
        first: document.querySelector(".item").getBoundingClientRect().top,
      }));
      assert(dim.scroll <= dim.width);
      assert(dim.first < 350);
      results.checks.push(
        "mobile " + width + " no overflow and feed above fold",
      );
      await page.screenshot({
        path: path.join(out, "mobile-" + width + ".png"),
      });
      await page.locator("#chatBtn").click();
      await page.waitForTimeout(100);
      const send = await page.locator("#chatSend").boundingBox();
      assert(send.x + send.width <= width);
      assert(send.y + send.height <= (width === 320 ? 568 : 844));
      await page.locator("#chatClose").click();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(".save-btn").first().click();
    await page.locator("#savedBtn").click();
    await page.waitForTimeout(200);
    assert((await page.locator(".item").count()) >= 1);
    results.checks.push("bookmark view works");
    await page.locator(".item-title").first().click();
    await page.locator("#article h1").waitFor();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: path.join(out, "detail.png") });
    const requestBodies = [];
    page.on("request", (r) => {
      if (r.url().includes("/api/chat")) requestBodies.push(r.postDataJSON());
    });
    await page.locator("#askCta").click();
    await page
      .locator("#chatInput")
      .fill("这篇资讯讲了什么？用两句话概括并注明来源。");
    await page.locator("#chatSend").click();
    await page.waitForFunction(
      () => !document.getElementById("chatSend").hidden,
      {},
      { timeout: 65000 },
    );
    results.chatText = await page.locator("#chatMsgs").innerText();
    results.chatStatus = await page.locator("#chatStatus").innerText();
    assert.equal(results.chatStatus, "");
    assert((await page.locator(".chat-msg.ai").count()) > 0);
    await page.screenshot({ path: path.join(out, "chat.png") });
    await page.route("**/api/chat", (r) =>
      r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ answer: "追问请求已验证。" }),
      }),
    );
    await page.locator("#chatInput").fill("它和上一代有什么变化？");
    await page.locator("#chatSend").click();
    await page.waitForFunction(
      () => !document.getElementById("chatSend").hidden && document.getElementById("chatMsgs").textContent.includes("追问请求已验证"),
    );
    assert.equal(requestBodies[1].history.length, 2);
    results.checks.push("live AI success and follow-up carries history");
    await page.goto(base + "/stock.html");
    await page.locator(".mkt-tabs").waitFor({ timeout: 25000 });
    await page.locator('.mkt-tab[data-mkt="US"]').click();
    await page.locator("#moreQuotes").click();
    await page.waitForFunction(
      () => !document.getElementById("moreQuotes")?.disabled,
      {},
      { timeout: 20000 },
    );
    assert.equal(await page.locator(".mkt-tab.active").innerText(), "美股");
    results.checks.push("market filter survives load more");
    assert.deepEqual(results.errors, []);
  } finally {
    fs.writeFileSync(
      path.join(out, "browser-results.json"),
      JSON.stringify(results, null, 2),
    );
    await browser.close();
  }
  console.log(JSON.stringify(results, null, 2));
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
