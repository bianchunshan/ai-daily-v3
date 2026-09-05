const { chromium } = require('/Users/steve/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const base = process.env.TEST_BASE || 'http://127.0.0.1:4193';
const out = path.resolve('.test-output/brand');
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const result = { base, checks: [], errors: [] };
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, colorScheme: 'light' });
    page.on('pageerror', e => result.errors.push(e.message));
    await page.goto(base);
    await page.locator('.item-title').first().waitFor();
    await page.locator('.brand-symbol').evaluate(img => img.decode());
    assert.equal(await page.locator('.brand-name').innerText(), '前序');
    assert((await page.title()).startsWith('前序'));
    assert((await page.locator('link[rel="icon"]').getAttribute('href')).includes('qianxu-symbol'));
    result.checks.push('new name, logo, page title and favicon');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: path.join(out, 'desktop-light.png') });
    await page.locator('#themeBtn').click();
    await page.screenshot({ path: path.join(out, 'desktop-dark.png') });
    await page.locator('#themeBtn').click();
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: width === 320 ? 568 : 844 });
      const layout = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth, logoRight: document.querySelector('.logo').getBoundingClientRect().right, toolsLeft: document.querySelector('.topbar-actions').getBoundingClientRect().left }));
      assert(layout.scroll <= width);
      assert(layout.logoRight < layout.toolsLeft);
      await page.screenshot({ path: path.join(out, 'mobile-' + width + '.png') });
      await page.locator('#chatBtn').click();
      const send = await page.locator('#chatSend').boundingBox();
      assert(send.x + send.width <= width);
      await page.locator('#chatClose').click();
      result.checks.push('mobile ' + width + ' brand and tools fit');
    }
    await page.locator('.item-title').first().click();
    await page.locator('#article h1').waitFor();
    assert.equal(await page.locator('.page-brand').innerText(), '前序');
    assert((await page.title()).endsWith(' · 前序'));
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: path.join(out, 'detail-mobile.png') });
    await page.goto(base + '/stock.html');
    assert.equal(await page.locator('.page-brand').innerText(), '前序');
    assert((await page.title()).includes('前序'));
    result.checks.push('detail and market brand consistency');
    if (base.includes('127.0.0.1')) {
      await page.setViewportSize({ width: 1200, height: 772 });
      await page.goto(base + '/design/qianxu-identity.html');
      await page.locator('.lockup img').evaluate(img => img.decode());
      await page.screenshot({ path: path.join(out, 'qianxu-identity.png') });
    }
    assert.deepEqual(result.errors, []);
  } finally {
    fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(result, null, 2));
    await browser.close();
  }
  console.log(JSON.stringify(result, null, 2));
})().catch(e => { console.error(e); process.exitCode = 1; });
