// AI 助手:基于今日资讯回答/分析。POST {question, context:[{title,summary,category}]}
// 用 Qwen(阿里云 Anthropic 兼容端点),key 取 Vercel 环境变量 QWEN_KEY。
const QWEN_URL = 'https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic/v1/messages';
const QWEN_MODEL = 'qwen3.7-max';

function readBody(req) {
  return new Promise((resolve) => {
    let d = '';
    req.on('data', (c) => (d += c));
    req.on('end', () => resolve(d));
    req.on('error', () => resolve(''));
  });
}

function stripHtml(s) {
  return String(s || '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/\s+/g, ' ')
    .trim();
}

function decodeDdgUrl(href) {
  if (!href) return '';
  try {
    const url = new URL(href, 'https://duckduckgo.com');
    const u = url.searchParams.get('uddg');
    return u || url.href;
  } catch (e) {
    return href;
  }
}

async function webSearch(query) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const url = 'https://duckduckgo.com/html/?q=' + encodeURIComponent(query);
    const r = await fetch(url, {
      headers: { 'user-agent': 'Mozilla/5.0' },
      signal: controller.signal,
    });
    const html = await r.text();
    const blocks = html.split('result__body').slice(1, 6);
    return blocks.map((b) => {
      const href = /class="result__a"[^>]+href="([^"]+)"/.exec(b);
      const title = /class="result__a"[^>]*>([\s\S]*?)<\/a>/.exec(b);
      const snippet = /class="result__snippet"[^>]*>([\s\S]*?)<\/a>/.exec(b) ||
        /class="result__snippet"[^>]*>([\s\S]*?)<\/div>/.exec(b);
      return {
        title: stripHtml(title && title[1]),
        snippet: stripHtml(snippet && snippet[1]),
        url: decodeDdgUrl(href && href[1]),
      };
    }).filter((x) => x.title || x.snippet);
  } catch (e) {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });
  const key = process.env.QWEN_KEY;
  if (!key) return res.status(500).json({ error: 'server missing QWEN_KEY' });

  let body = req.body;
  if (body === undefined || body === null) {
    const raw = await readBody(req);
    try { body = JSON.parse(raw); } catch (e) { body = {}; }
  }
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch (e) { body = {}; } }

  const question = String((body && body.question) || '').trim().slice(0, 500);
  if (!question) return res.status(400).json({ error: 'empty question' });

  const ctx = Array.isArray(body && body.context) ? body.context.slice(0, 80) : [];
  const ctxText = ctx
    .map((n, i) => `${i + 1}. [${n.category || ''}] ${n.title || ''}｜${String(n.summary || '').slice(0, 120)}${n.url ? `｜${n.url}` : ''}`)
    .join('\n');

  const searchResults = await webSearch(`${question} 最新 科技 新闻`);
  const searchText = searchResults.length
    ? searchResults.map((r, i) => `${i + 1}. ${r.title}｜${r.snippet}｜${r.url}`).join('\n')
    : '无可用网页检索结果。';

  const system = '你是「前沿科技日报」的 AI 助手。用户会给你站内资讯和网页检索结果。你应先判断问题需要什么信息,再决定如何回答。' +
    '不要只机械复述列表;如果站内资讯不足,结合网页检索结果和常识补足,并明确哪些来自站内资讯、哪些来自检索或常识。' +
    '中文回答。可以自然组织结构,但需要给出简短的“判断过程/依据”,说明你用了哪些信息、是否检索、还有什么不确定。';
  const prompt = `站内资讯(共${ctx.length}条):\n${ctxText}\n\n网页检索结果:\n${searchText}\n\n用户问题:${question}`;

  try {
    const r = await fetch(QWEN_URL, {
      method: 'POST',
      headers: { 'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
      body: JSON.stringify({ model: QWEN_MODEL, max_tokens: 1600, system, messages: [{ role: 'user', content: prompt }] }),
    });
    const d = await r.json();
    if (!r.ok) return res.status(502).json({ error: d.error || `qwen HTTP ${r.status}` });
    const answer = (d.content || []).map((b) => (b && b.text) || '').join('').trim();
    if (!answer) return res.status(502).json({ error: 'no model answer' });
    return res.status(200).json({ answer });
  } catch (e) {
    return res.status(502).json({ error: String(e) });
  }
};
