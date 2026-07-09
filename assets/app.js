/* ===== 前沿科技日报 · 共享逻辑 ===== */
(function (global) {
  'use strict';

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
  var ASSET_VER = '20260709b';
  var RAW_BASE = 'https://raw.githubusercontent.com/bianchunshan/ai-daily-v3/main';
  var DEFAULT_LIST_URL = RAW_BASE + '/news_data_list.js';
  var DEFAULT_FULL_URL = RAW_BASE + '/news_data_latest.js';
  var DEFAULT_BODIES_URL = RAW_BASE + '/news_bodies.json';

  function catMeta(name) { return CATS[name] || DEFAULT_CAT; }

  function coverHTML(news, opts) {
    opts = opts || {};
    var c = catMeta(news.category);
    var showLabel = opts.label !== false;
    var seed = hashStr((news.title || '') + news.id);
    var angle = 95 + (seed % 90);
    var hx = 15 + (seed % 70);
    var hy = 10 + ((seed >> 3) % 50);
    var bg =
      'background:' +
        'radial-gradient(circle at ' + hx + '% ' + hy + '%, rgba(255,255,255,.28), rgba(255,255,255,0) 55%),' +
        'linear-gradient(' + angle + 'deg,' + c.from + ' 0%,' + c.to + ' 100%);';
    var html = '<div class="cover" style="' + bg + '">';
    html += '<span class="glyph">' + c.icon + '</span>';
    var img = safeUrl(news.image);
    if (img) html += '<img class="photo" loading="lazy" src="' + esc(img) + '" onerror="this.remove()" alt="">';
    if (showLabel) html += '<span class="ct">' + esc(news.category) + '</span>';
    html += '</div>';
    return html;
  }

  function hashStr(s) {
    var h = 5381;
    for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
    return h;
  }

  function heat(news) {
    var score = 40;
    var mins = ageMinutes(news.ts);
    if (mins != null) {
      if (mins < 60) score += 45;
      else if (mins < 360) score += 35;
      else if (mins < 1440) score += 25;
      else if (mins < 4320) score += 12;
      else if (mins < 10080) score += 4;
    }
    var src = String(news.source || '');
    if (/路透|彭博|Reuters|Bloomberg|财新|华尔街日报|WSJ|FT|Financial Times/i.test(src)) score += 18;
    else if (/TechCrunch|The Verge|Wired|MIT|Nature|Science|IEEE/i.test(src)) score += 14;
    else if (/36氪|虎嗅|极客公园|量子位|机器之心|蓝鲸|澎湃|新浪|腾讯|网易/i.test(src)) score += 8;
    var stocks = news.stocks || [];
    var strong = 0;
    for (var i = 0; i < stocks.length; i++) {
      if (stocks[i] && stocks[i].confidence !== 'low') strong++;
    }
    score += Math.min(18, strong * 6);
    if ((news.tags || []).length) score += Math.min(8, (news.tags || []).length * 2);
    if (news.body || news.summary) score += 4;
    score += hashStr((news.title || '') + news.id) % 7;
    return Math.max(10, Math.min(99, Math.round(score)));
  }

  function ageMinutes(ts) {
    if (!ts) return null;
    var d = new Date(ts);
    if (isNaN(d.getTime())) return null;
    return Math.floor((Date.now() - d.getTime()) / 60000);
  }

  function comments(news) {
    var base = hashStr('c' + (news.title || '') + news.id);
    return base % 320;
  }

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

  function parseNewsModule(txt) {
    var data = new Function(
      txt + '\n;return {' +
      'newsData: (typeof newsData !== "undefined" && Array.isArray(newsData)) ? newsData : [],' +
      'newsDigest: (typeof newsDigest !== "undefined") ? newsDigest : null' +
      '};'
    )();
    return data || { newsData: [], newsDigest: null };
  }

  function fetchText(url, timeoutMs) {
    var controller = global.AbortController ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, timeoutMs || 8000) : null;
    return fetch(url + (url.indexOf('?') >= 0 ? '&' : '?') + 't=' + Date.now(), {
      cache: 'no-store',
      signal: controller && controller.signal
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    }).finally(function () {
      if (timer) clearTimeout(timer);
    });
  }

  function loadScript(src, timeoutMs) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      var done = false;
      var timer = setTimeout(function () {
        if (done) return;
        done = true;
        reject(new Error('timeout'));
      }, timeoutMs || 12000);
      s.src = src;
      s.onload = function () {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve();
      };
      s.onerror = function () {
        if (done) return;
        done = true;
        clearTimeout(timer);
        reject(new Error('load failed'));
      };
      document.body.appendChild(s);
    });
  }

  function takeGlobalNews() {
    var data = (typeof global.newsData !== 'undefined' && global.newsData && global.newsData.length)
      ? global.newsData
      : ((typeof newsData !== 'undefined' && newsData && newsData.length) ? newsData : null);
    var digest = (typeof global.newsDigest !== 'undefined')
      ? global.newsDigest
      : ((typeof newsDigest !== 'undefined') ? newsDigest : null);
    return { data: data, digest: digest };
  }

  function loadBundledNews(fallback, cb) {
    loadScript('news_data_list.js?v=' + ASSET_VER, 12000).then(function () {
      var got = takeGlobalNews();
      if (got.data) { cb(got.data, got.digest); return; }
      return loadScript('news_data_latest.js?v=' + ASSET_VER, 15000).then(function () {
        var full = takeGlobalNews();
        cb(full.data || fallback, full.digest);
      });
    }).catch(function () {
      loadScript('news_data_latest.js?v=' + ASSET_VER, 15000).then(function () {
        var full = takeGlobalNews();
        cb(full.data || fallback, full.digest);
      }).catch(function () { cb(fallback, null); });
    });
  }

  // 优先 GitHub raw 轻量列表 → 全量 raw → 部署包内 → 兜底
  function loadNews(fallback, cb) {
    if (!global.fetch) {
      loadBundledNews(fallback, cb);
      return;
    }
    var listUrl = global.AID_NEWS_LIST_URL || global.AID_NEWS_DATA_URL || DEFAULT_LIST_URL;
    var fullUrl = global.AID_NEWS_FULL_URL || DEFAULT_FULL_URL;

    fetchText(listUrl, 8000).then(function (txt) {
      var parsed = parseNewsModule(txt);
      if (parsed.newsData && parsed.newsData.length) {
        cb(parsed.newsData, parsed.newsDigest || null);
        return;
      }
      throw new Error('empty list');
    }).catch(function () {
      return fetchText(fullUrl, 12000).then(function (txt) {
        var parsed = parseNewsModule(txt);
        if (parsed.newsData && parsed.newsData.length) {
          cb(parsed.newsData, parsed.newsDigest || null);
          return;
        }
        throw new Error('empty full');
      });
    }).catch(function () {
      loadBundledNews(fallback, cb);
    });
  }

  function findNewsById(list, id, cb) {
    var hit = null;
    for (var i = 0; i < (list || []).length; i++) {
      if (String(list[i].id) === String(id)) { hit = list[i]; break; }
    }
    if (hit) { cb(hit); return; }
    var fullUrl = global.AID_NEWS_FULL_URL || DEFAULT_FULL_URL;
    if (!global.fetch) { cb(null); return; }
    fetchText(fullUrl, 20000).then(function (txt) {
      var parsed = parseNewsModule(txt);
      var full = parsed.newsData || [];
      for (var j = 0; j < full.length; j++) {
        if (String(full[j].id) === String(id)) { cb(full[j]); return; }
      }
      cb(null);
    }).catch(function () { cb(null); });
  }

  var bodyCache = null;
  var bodyPromise = null;

  function loadBodies() {
    if (bodyCache) return Promise.resolve(bodyCache);
    if (bodyPromise) return bodyPromise;
    var url = global.AID_NEWS_BODIES_URL || DEFAULT_BODIES_URL;
    bodyPromise = fetch(url + '?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('bodies ' + r.status);
        return r.json();
      })
      .then(function (d) { bodyCache = d || {}; return bodyCache; })
      .catch(function () {
        return fetch('news_bodies.json?v=' + ASSET_VER)
          .then(function (r) { if (!r.ok) throw new Error('local bodies'); return r.json(); })
          .then(function (d) { bodyCache = d || {}; return bodyCache; })
          .catch(function () { bodyCache = {}; return bodyCache; });
      });
    return bodyPromise;
  }

  function loadBody(id) {
    return loadBodies().then(function (map) {
      return map[String(id)] || '';
    });
  }

  function stockTag(s) {
    if (!s || !s.name) return '';
    if (s.confidence === 'low') return '';
    var label = esc(s.name) + (s.ticker ? ' ' + esc(s.ticker) : '');
    var href = s.ticker ? 'stock.html?symbol=' + encodeURIComponent(s.ticker) : 'stock.html';
    var title = s.reason ? ' title="' + esc(s.reason) + '"' : '';
    return '<a class="stock-pill rel" href="' + href + '" onclick="event.stopPropagation()"' + title + '>📈 ' + label + '</a>';
  }

  function strongStocks(news) {
    return (news.stocks || []).filter(function (s) { return s && s.name && s.confidence !== 'low'; });
  }

  function ensureChatUI() {
    if (document.getElementById('chatPanel')) return;
    var mask = document.createElement('div');
    mask.className = 'chat-mask';
    mask.id = 'chatMask';
    var panel = document.createElement('div');
    panel.className = 'chat-panel';
    panel.id = 'chatPanel';
    panel.innerHTML =
      '<div class="chat-head"><span class="t">🤖 问AI</span><span class="sub">基于今日资讯</span><span class="x" id="chatClose">×</span></div>' +
      '<div class="chat-msgs" id="chatMsgs"></div>' +
      '<div class="chat-sugs" id="chatSugs"></div>' +
      '<div class="chat-input"><input id="chatInput" placeholder="问问今天的资讯…" maxlength="500" autocomplete="off"><button id="chatSend">发送</button></div>';
    document.body.appendChild(mask);
    document.body.appendChild(panel);
  }

  var chatBusy = false;
  var chatSeed = null;

  function addMsg(cls, text) {
    var d = document.createElement('div');
    d.className = 'chat-msg ' + cls;
    d.textContent = text;
    var box = document.getElementById('chatMsgs');
    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
    return d;
  }

  function renderSugs(list) {
    document.getElementById('chatSugs').innerHTML = list.map(function (s) {
      return '<span class="chat-sug">' + esc(s) + '</span>';
    }).join('');
    document.querySelectorAll('#chatSugs .chat-sug').forEach(function (el) {
      el.onclick = function () {
        document.getElementById('chatInput').value = el.textContent;
        sendChat();
      };
    });
  }

  async function sendChat() {
    if (chatBusy) return;
    var inp = document.getElementById('chatInput');
    var q = inp.value.trim();
    if (!q) return;
    document.getElementById('chatSugs').innerHTML = '';
    addMsg('me', q);
    inp.value = '';
    chatBusy = true;
    document.getElementById('chatSend').disabled = true;
    var tip = addMsg('tip', '思考中…');
    try {
      var headers = { 'content-type': 'application/json' };
      var token = '';
      try { token = localStorage.getItem('chat_token') || ''; } catch (e) {}
      if (token) headers['x-chat-token'] = token;
      var r = await fetch('/api/chat', {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ question: q, focusId: chatSeed && chatSeed.id })
      });
      var raw = await r.text();
      var d = {};
      try { d = raw ? JSON.parse(raw) : {}; } catch (e) { d = { error: raw.slice(0, 120) }; }
      tip.remove();
      addMsg('ai', r.ok && d.answer ? d.answer : '抱歉,出错了:' + (d.error || ('HTTP ' + r.status)));
    } catch (e) {
      tip.remove();
      addMsg('ai', '请求失败:' + e);
    }
    chatBusy = false;
    document.getElementById('chatSend').disabled = false;
  }

  function openChat(opts) {
    opts = opts || {};
    ensureChatUI();
    chatSeed = opts.focus || null;
    document.getElementById('chatMask').classList.add('open');
    document.getElementById('chatPanel').classList.add('open');
    var msgs = document.getElementById('chatMsgs');
    if (!msgs.children.length) {
      var intro = chatSeed
        ? '可以围绕「' + (chatSeed.title || '这篇资讯') + '」提问,或问今天的其他科技动态。'
        : '我是「前沿科技日报」的 AI 助手,可以基于今日资讯帮你问答、归纳或分析。试试下面的问题,或直接问我。';
      addMsg('ai', intro);
      var sugs = chatSeed
        ? ['这篇的核心影响是什么?', '关联哪些产业链环节?', '还有哪些类似进展?']
        : ['今天最值得关注的 3 件事', 'AI 基础设施有什么新进展?', '半导体和先进制造有哪些变化?', '地缘科技对产业链有什么影响?'];
      renderSugs(sugs);
    }
    setTimeout(function () {
      var inp = document.getElementById('chatInput');
      if (inp) inp.focus();
    }, 250);
  }

  function closeChat() {
    var mask = document.getElementById('chatMask');
    var panel = document.getElementById('chatPanel');
    if (mask) mask.classList.remove('open');
    if (panel) panel.classList.remove('open');
  }

  function bindChatControls() {
    ensureChatUI();
    var close = document.getElementById('chatClose');
    var mask = document.getElementById('chatMask');
    var send = document.getElementById('chatSend');
    var inp = document.getElementById('chatInput');
    if (close) close.onclick = closeChat;
    if (mask) mask.onclick = closeChat;
    if (send) send.onclick = sendChat;
    if (inp) inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') sendChat(); });
  }

  global.AID = {
    catMeta: catMeta, coverHTML: coverHTML, heat: heat, comments: comments,
    esc: esc, getParam: getParam, initTheme: initTheme, toggleTheme: toggleTheme,
    loadNews: loadNews, findNewsById: findNewsById, loadBody: loadBody,
    stockTag: stockTag, strongStocks: strongStocks,
    relTime: relTime, safeUrl: safeUrl, openChat: openChat, closeChat: closeChat,
    bindChatControls: bindChatControls, catOrder: CAT_ORDER.slice(), assetVer: ASSET_VER
  };
})(window);
