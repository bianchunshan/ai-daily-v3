/* ===== 前沿科技日报 · 共享逻辑 ===== */
(function (global) {
  'use strict';

  // 分类 -> 封面配色 + 图标。未知分类用 default。
  var CATS = {
    '人工智能': { icon: '🤖', from: '#6a5cff', to: '#9b4dff' },
    '商业航天': { icon: '🚀', from: '#4f46e5', to: '#7c3aed' },
    '国际局势': { icon: '🌐', from: '#334155', to: '#0f766e' },
    '量子科技': { icon: '⚛️', from: '#d946ef', to: '#7c3aed' },
    '机器人': { icon: '🦾', from: '#f97316', to: '#ef4444' },
    '生物医药': { icon: '🧬', from: '#10b981', to: '#0891b2' },
    '未来能源': { icon: '⚡', from: '#f59e0b', to: '#ef4444' },
    '消费电子': { icon: '📱', from: '#ec4899', to: '#8b5cf6' }
  };
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

  // 加载数据：优先外部 news_data_latest.js（每日 Action 更新），失败用内置兜底。
  // 回调 cb(newsList, digest)，digest 可能为 null。
  function loadNews(fallback, cb) {
    var s = document.createElement('script');
    var done = false;
    var timer = setTimeout(function () {
      if (done) return;
      done = true;
      cb(fallback, null);
    }, 12000);
    s.src = 'news_data_latest.js';
    s.onload = function () {
      if (done) return;
      done = true;
      clearTimeout(timer);
      var data = (typeof newsData !== 'undefined' && newsData.length) ? newsData : fallback;
      var digest = (typeof newsDigest !== 'undefined') ? newsDigest : null;
      cb(data, digest);
    };
    s.onerror = function () {
      if (done) return;
      done = true;
      clearTimeout(timer);
      cb(fallback, null);
    };
    document.body.appendChild(s);
  }

  // 关联标的标签：只展示 名称(+代码)，鼠标悬停看关联理由；绝不显示价格/涨跌
  function stockTag(s) {
    if (!s || !s.name) return '';
    var label = esc(s.name) + (s.ticker ? ' ' + esc(s.ticker) : '');
    var href = s.ticker ? 'stock.html?symbol=' + encodeURIComponent(s.ticker) : 'stock.html';
    var title = s.reason ? ' title="' + esc(s.reason) + '"' : '';
    // stopPropagation:别让点击冒泡到新闻卡片的"进详情"
    return '<a class="stock-pill rel" href="' + href + '" onclick="event.stopPropagation()"' + title + '>📈 ' + label + '</a>';
  }

  global.AID = {
    catMeta: catMeta, coverHTML: coverHTML, heat: heat, comments: comments,
    esc: esc, getParam: getParam, initTheme: initTheme, toggleTheme: toggleTheme,
    loadNews: loadNews, stockTag: stockTag, relTime: relTime, safeUrl: safeUrl
  };
})(window);
