const test = require('node:test');
const assert = require('node:assert/strict');
const { webSearch, relevant } = require('../lib/web-search');

test('Web search rejects unrelated results and honors site filters', () => {
  const items = [
    { title: 'Indeed jobs', summary: 'Jobs today', url: 'https://indeed.com' },
    { title: 'WebGLRenderer docs', summary: '', url: 'https://threejs.org/docs/pages/WebGLRenderer.html' },
    { title: 'WebGLRenderer docs', summary: '', url: 'https://unrelated.org/docs' },
    { title: 'WebGLRenderer', url: 'javascript:alert(1)' },
  ];
  assert.deepEqual(relevant(items, 'site:threejs.org WebGLRenderer'), [items[1]]);
  assert.deepEqual(relevant([items[0]], '英伟达最新进展'), []);
});

test('DuckDuckGo HTML uses structured parsing and decodes redirect URLs', async t => {
  t.mock.method(global, 'fetch', async () => new Response('<div class="result__body"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fthreejs.org%2Fdocs%2Fpages%2FWebGLRenderer.html&amp;rut=x">WebGLRenderer - three.js docs</a><a class="result__snippet">Official &amp; complete.</a></div>'));
  const result = await webSearch('Three.js WebGLRenderer documentation');
  assert.equal(result[0].url, 'https://threejs.org/docs/pages/WebGLRenderer.html');
  assert.equal(result[0].summary, 'Official & complete.');
});

test('Unrelated fallback RSS results are not exposed as evidence', async t => {
  let calls = 0;
  t.mock.method(global, 'fetch', async () => new Response(++calls === 1 ? '<html>Unavailable</html>' : '<rss><channel><item><title>Crowell weather</title><link>https://example.com/weather</link><description>Weather</description></item></channel></rss>'));
  assert.deepEqual(await webSearch('英伟达最新进展'), []);
  assert.equal(calls, 2);
});

test('Kimi search uses the official service and returns dated evidence', async t => {
  const oldKey = process.env.KIMI_KEY;
  process.env.KIMI_KEY = 'test-kimi-key';
  t.after(() => { if (oldKey === undefined) delete process.env.KIMI_KEY; else process.env.KIMI_KEY = oldKey; });
  t.mock.method(global, 'fetch', async (url, options) => {
    assert.equal(url, 'https://api.kimi.com/coding/v1/search');
    assert.equal(options.headers.Authorization, 'Bearer test-kimi-key');
    assert.equal(JSON.parse(options.body).text_query, 'WebGLRenderer docs');
    return new Response(JSON.stringify({ search_results: [{ title: 'WebGLRenderer', url: 'https://threejs.org/docs/pages/WebGLRenderer.html', snippet: 'Official renderer API', site_name: 'Three.js', date: '2026-09-05' }] }));
  });
  const results = await webSearch('WebGLRenderer docs');
  assert.equal(results[0].source, 'Three.js');
  assert.equal(results[0].date, '2026-09-05');
});
