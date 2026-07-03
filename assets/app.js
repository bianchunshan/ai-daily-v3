/* ===== 前沿科技日报 · 共享逻辑 ===== */
(function (global) {
  'use strict';

  // 分类 -> 封面配色 + 图标。未知分类用 default。
  var CATS = {
    '人工智能': { icon: '🤖', from: '#2563eb', to: '#7c3aed' },
    'AI 基础设施': { icon: '🖥️', from: '#0f766e', to: '#2563eb' },
    '半导体与先进制造': { icon: '🔬', from: '#475569', to: '#0284c7' },
    '机器人': { icon: '🦾', from: '#f97316', to: '#dc2626' },
    '商业航天': { icon: '🚀', from: '#1d4ed8', to: '#0f172a' },
    '生物医药': { icon: '🧬', from: '#10b981', to: '#0891b2' },
    '量子科技': { icon: '⚛️', from: '#7c3aed', to: '#0e7490' },
    '未来能源': { icon: '⚡', from: '#f59e0b', to: '#16a34a' },
    '新材料': { icon: '⬡', from: '#64748b', to: '#14b8a6' },
    '脑机接口': { icon: '🧠', from: '#be123c', to: '#7c2d12' },
    '网络安全': { icon: '🔐', from: '#334155', to: '#111827' },
    '消费电子': { icon: '📱', from: '#db2777', to: '#7c3aed' },
    '地缘科技': { icon: '🌐', from: '#374151', to: '#0f766e' }
  };
  var CAT_ORDER = ['人工智能', 'AI 基础设施', '半导体与先进制造', '机器人', '商业航天',
    '生物医药', '量子科技', '未来能源', '新材料', '脑机接口', '网络安全', '消费电子', '地缘科技'];
  var DEFAULT_CAT = { icon: '📰', from: '#64748b', to: '#475569' };

  function catMeta(name) { return CATS[name] || DEFAULT_CAT; }

  // 生成纯 CSS 封面 HTML（无版权风险）。同分类保持色系+图标，按 id 做确定性微变化，避免千篇一律
  function coverHTML(news, opts) {
    opts = opts || {};
    var c = catMeta(news.category);
    var showLabel = opts.label !== false;
    var seed = hashStr((news.title || '') + news.id);
    var angle = 95 + (seed % 90);                 // 95~184deg
    var hx = 15 + (seed % 70);                     // 高光横向 15%~85%
    var hy = 10 + ((seed >> 3) % 50);              // 高光纵向 10%~60%
    var bg =
      'background:' +
        'radial-gradient(circle at ' + hx + '% ' + hy + '%, rgba(255,255,255,.28), rgba(255,255,255,0) 55%),' +
        'linear-gradient(' + angle + 'deg,' + c.from + ' 0%,' + c.to + ' 100%);';
    var html = '<div class="cover" style="' + bg + '">';
    html += '<span class="glyph">' + c.icon + '</span>';
    // 有真实配图就叠在渐变封面之上;加载失败 onerror 移除 → 自动露出分类封面
    var img = safeUrl(news.image);
    if (img) html += '<img class="photo" loading="lazy" src="' + esc(img) + '" onerror="this.remove()" alt="">';
    if (showLabel) html += '<span class="ct">' + esc(news.category) + '</span>';
    html += '</div>';
    return html;
  }

  // 稳定的"热度/评论数"——同一条新闻每次一致，纯 UI 装饰
  function hashStr(s) {
    var h = 5381;
    for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
    return h;
  }
  function heat(news) {
    var base = hashStr((news.title || '') + news.id);
    return (base % 900) + 100; // 100~999
  }
  function comments(news) {
    var base = hashStr('c' + (news.title || '') + news.id);
    return base % 320;
  }

  // 从 ISO 时间戳算新鲜的相对时间;无法解析时返回空(调用方回退到存储的 time 字符串)
  function relTime(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    if (isNaN(d.getTime())) return '';
    var mins = Math.floor((Date.now() - d.getTime()) / 60000);
    if (mins < 1) return '刚刚';
    if (mins < 60) return mins + '分钟前';
    if (mins < 1440) return Math.floor(mins / 60) + '小时前';
    return Math.floor(mins / 1440) + '天前';
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function safeUrl(url) {
    try {
      var u = new URL(String(url || ''), global.location.href);
      return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : '';
    } catch (e) {
      return '';
    }
  }

  function getParam(name) {
    var m = new RegExp('[?&]' + name + '=([^&#]*)').exec(global.location.href);
    if (!m) return null;
    try { return decodeURIComponent(m[1]); } catch (e) { return null; }
  }

  // 主题：初始跟随系统，可切换并记忆
  function initTheme() {
    var saved = null;
    try { saved = localStorage.getItem('theme'); } catch (e) {}
    var dark = saved ? saved === 'dark'
      : (global.matchMedia && global.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  }
  function toggleTheme() {
    var cur = document.documentElement.getAttribute('data-theme');
    var next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('theme', next); } catch (e) {}
    return next;
  }

  // 数据与站点同源部署(data/*.json),走浏览器 ETag 协商缓存,无需 cache-buster。
  function fetchJSON(url, timeoutMs) {
    var controller = global.AbortController ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, timeoutMs || 15000) : null;
    return fetch(url, { signal: controller && controller.signal }).then(function (r) {
      if (timer) clearTimeout(timer);
      if (!r.ok) throw new Error(url + ' HTTP ' + r.status);
      return r.json();
    }, function (e) {
      if (timer) clearTimeout(timer);
      throw e;
    });
  }

  // 加载新闻索引:先取小的热索引(index-hot.json)快速首屏,再后台补全量(index.json)。
  // 回调 cb(newsList, digest, done);done=false 表示热索引先到、全量稍后还会再回调一次。
  function loadNews(fallback, cb) {
    function digestOf(d) { return (d && d.digest && d.digest.text) ? d.digest : null; }
    fetchJSON('data/index-hot.json', 10000).then(function (hot) {
      if (!hot || !hot.items || !hot.items.length) throw new Error('empty hot index');
      cb(hot.items, digestOf(hot), false);
      fetchJSON('data/index.json', 30000).then(function (full) {
        if (full && full.items && full.items.length >= hot.items.length) {
          cb(full.items, digestOf(full) || digestOf(hot), true);
        }
      }).catch(function () {});
    }).catch(function () {
      // 热索引失败(比如老部署),直接尝试全量,再不行用内置兜底
      fetchJSON('data/index.json', 30000).then(function (full) {
        if (full && full.items && full.items.length) cb(full.items, digestOf(full), true);
        else cb(fallback, null, true);
      }).catch(function () { cb(fallback, null, true); });
    });
  }

  // 详情条目按 id 前 2 位分片存放,详情页只取所在分片(~几十 KB)。
  function loadItem(id, cb) {
    id = String(id || '');
    if (!/^[0-9a-f]{6,}$/.test(id)) { cb(null); return; }
    fetchJSON('data/items/' + id.slice(0, 2) + '.json', 15000).then(function (shard) {
      cb((shard && shard[id]) || null);
    }).catch(function () { cb(null); });
  }

  // 关联标的标签：只展示 名称(+代码)，鼠标悬停看关联理由；绝不显示价格/涨跌
  // 新闻卡片本身是 <a>,这里用 span+跳转避免嵌套链接;stopPropagation 防止触发卡片"进详情"
  function stockTag(s) {
    if (!s || !s.name) return '';
    var label = esc(s.name) + (s.ticker ? ' ' + esc(s.ticker) : '');
    var href = s.ticker ? 'stock.html?symbol=' + encodeURIComponent(s.ticker) : 'stock.html';
    var title = s.reason ? ' title="' + esc(s.reason) + '"' : '';
    return '<span class="stock-pill rel" role="link" tabindex="0"' + title +
      ' onclick="event.stopPropagation();event.preventDefault();location.href=\'' + href + '\'">📈 ' + label + '</span>';
  }

  global.AID = {
    catMeta: catMeta, coverHTML: coverHTML, heat: heat, comments: comments,
    esc: esc, getParam: getParam, initTheme: initTheme, toggleTheme: toggleTheme,
    loadNews: loadNews, loadItem: loadItem, fetchJSON: fetchJSON,
    stockTag: stockTag, relTime: relTime, safeUrl: safeUrl,
    catOrder: CAT_ORDER.slice()
  };
})(window);
