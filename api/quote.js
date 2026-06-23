// 实时行情代理(新浪财经,免费、无需 key)。支持 ?symbol=NVDA,0700.HK,600519.SH 批量。
// 返回 { quotes:[{symbol,name,market,currency,price,changePercent,time,source}], note }
// 说明:A股/港股盘中接近实时,美股约 15 分钟延迟;新浪为非官方接口。

function toSina(raw) {
  const sym = String(raw || '').trim().toUpperCase();
  if (!sym) return null;
  if (sym.endsWith('.HK')) return { sina: 'hk' + sym.slice(0, -3).padStart(5, '0'), market: 'HK', symbol: sym };
  if (sym.endsWith('.SH') || sym.endsWith('.SS')) return { sina: 'sh' + sym.slice(0, -3), market: 'CN', symbol: sym };
  if (sym.endsWith('.SZ')) return { sina: 'sz' + sym.slice(0, -3), market: 'CN', symbol: sym };
  if (/^\d{6}$/.test(sym)) return { sina: (sym[0] === '6' ? 'sh' : 'sz') + sym, market: 'CN', symbol: sym };
  if (/^[A-Z.]{1,6}$/.test(sym)) return { sina: 'gb_' + sym.replace('.', '$').toLowerCase(), market: 'US', symbol: sym };
  return null;
}

function parseLine(market, payload) {
  const f = payload.split(',');
  let name, price, prevClose, changePct, time, currency;
  if (market === 'CN') {
    if (f.length < 32) return null;
    name = f[0]; price = +f[3]; prevClose = +f[2];
    changePct = prevClose ? ((price - prevClose) / prevClose) * 100 : 0;
    time = (f[30] || '') + ' ' + (f[31] || ''); currency = '¥';
  } else if (market === 'HK') {
    if (f.length < 19) return null;
    name = f[1] || f[0]; price = +f[6]; changePct = +f[8]; prevClose = +f[3];
    time = (f[17] || '') + ' ' + (f[18] || ''); currency = 'HK$';
  } else { // US
    if (f.length < 4) return null;
    name = f[0]; price = +f[1]; changePct = +f[2]; time = f[3]; currency = '$';
  }
  if (!price || isNaN(price)) return null;
  return { name, market, currency, price, changePercent: Math.round(changePct * 100) / 100, time, source: '新浪财经' };
}

module.exports = async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'GET only' });
  const q = (req.query.symbol || '').trim();
  if (!q) return res.status(400).json({ error: 'missing symbol' });

  const reqs = q.split(',').map(toSina).filter(Boolean).slice(0, 30);
  if (!reqs.length) return res.status(400).json({ error: 'invalid symbol', input: q });

  try {
    const list = reqs.map(r => r.sina).join(',');
    const controller = new AbortController();
    let timer = setTimeout(() => controller.abort(), 5000);
    const r = await fetch('https://hq.sinajs.cn/list=' + list, {
      headers: { 'Referer': 'https://finance.sina.com.cn', 'User-Agent': 'Mozilla/5.0' },
      signal: controller.signal,
    }).finally(() => { if (timer) { clearTimeout(timer); timer = null; } });
    if (!r.ok) return res.status(502).json({ error: 'quote upstream bad status', status: r.status });
    const buf = await r.arrayBuffer();
    const text = new TextDecoder('gbk').decode(new Uint8Array(buf));

    const bySina = {};
    for (const m of text.matchAll(/hq_str_([^=]+)="([^"]*)"/g)) bySina[m[1]] = m[2];

    const quotes = [];
    for (const item of reqs) {
      const payload = bySina[item.sina];
      if (!payload) continue;
      const parsed = parseLine(item.market, payload);
      if (parsed) quotes.push({ symbol: item.symbol, ...parsed });
    }

    res.setHeader('Cache-Control', 's-maxage=30, stale-while-revalidate=120');
    return res.status(200).json({
      quotes,
      note: 'A股/港股盘中接近实时,美股约延迟15分钟 · 来源:新浪财经',
    });
  } catch (e) {
    return res.status(502).json({ error: String(e), input: q });
  }
}
