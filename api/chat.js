// AI 助手:基于今日资讯回答/分析。POST {question, context:[{title,summary,category}]}
// 用 Qwen(阿里云 Anthropic 兼容端点),key 取 Vercel 环境变量 QWEN_KEY。
const QWEN_URL = 'https://token-plan.cn-beijing.maas.aliyuncs.com/apps/anthropic/v1/messages';
const QWEN_MODEL = 'qwen3.7-max';
const QWEN_TIMEOUT_MS = 18000;

function readBody(req) {
  return new Promise((resolve) => {
    let d = '';
    req.on('data', (c) => (d += c));
    req.on('end', () => resolve(d));
    req.on('error', () => resolve(''));
  });
}

function fallbackAnswer(question, ctx) {
  if (!ctx.length) return '暂时没有可用的今日资讯上下文。';
  const picks = ctx.slice(0, 5);
  const lines = picks.map((n, i) => `${i + 1}. ${n.title || '未命名资讯'}${n.category ? `（${n.category}）` : ''}`);
  return [
    'AI 响应较慢,先按最新资讯给你一个本地摘要:',
    '',
    ...lines,
    '',
    question.includes('标的')
      ? '关联标的需要模型进一步判断,建议稍后再问一次。'
      : '这不是模型完整分析,但可以先帮你快速扫到当前最靠前的重点。'
  ].join('\n');
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

  const ctx = Array.isArray(body && body.context) ? body.context.slice(0, 12) : [];
  const ctxText = ctx
    .map((n, i) => `${i + 1}. [${n.category || ''}] ${n.title || ''}｜${String(n.summary || '').slice(0, 60)}`)
    .join('\n');

  const system = '你是「前沿科技日报」的 AI 助手。优先依据用户提供的今日资讯列表回答问题或做分析,' +
    '不要编造资讯里没有的具体事实;若资讯里没有相关内容,如实说明,可做合理的常识性补充但要标明。中文回答,简洁有条理。';
  const prompt = `今日资讯列表(共${ctx.length}条):\n${ctxText}\n\n用户问题:${question}`;

  let timer = null;
  try {
    const controller = new AbortController();
    timer = setTimeout(() => controller.abort(), QWEN_TIMEOUT_MS);
    const r = await fetch(QWEN_URL, {
      method: 'POST',
      headers: { 'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
      body: JSON.stringify({ model: QWEN_MODEL, max_tokens: 600, system, messages: [{ role: 'user', content: prompt }] }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    timer = null;
    const d = await r.json();
    const answer = (d.content || []).map((b) => (b && b.text) || '').join('').trim();
    if (!answer) return res.status(200).json({ answer: fallbackAnswer(question, ctx), fallback: true });
    return res.status(200).json({ answer });
  } catch (e) {
    if (timer) clearTimeout(timer);
    return res.status(200).json({ answer: fallbackAnswer(question, ctx), fallback: true, error: String(e) });
  }
};
