(function (global) {
  "use strict";
  var cats = [
    "人工智能",
    "AI 基础设施",
    "半导体与先进制造",
    "机器人",
    "商业航天",
    "生物医药",
    "量子科技",
    "未来能源",
    "新材料",
    "脑机接口",
    "网络安全",
    "消费电子",
    "地缘科技",
  ];
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  function safeUrl(s) {
    if (!String(s || "").trim() || s === "#") return "";
    try {
      var u = new URL(s, location.href);
      return /^https?:$/.test(u.protocol) ? u.href : "";
    } catch (e) {
      return "";
    }
  }
  function icon(name) {
    return (
      '<span class="ui-icon" aria-hidden="true" style="--icon:url(/assets/icons/' +
      name +
      '.svg)"></span>'
    );
  }
  function dateLabel(ts) {
    if (!ts) return "";
    var d = new Date(ts);
    return isNaN(+d)
      ? ""
      : d.toLocaleString("zh-CN", {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        });
  }
  function relTime(ts) {
    if (!ts) return "";
    var mins = Math.max(0, Math.floor((Date.now() - Date.parse(ts)) / 60000));
    if (!Number.isFinite(mins)) return "";
    return mins < 1
      ? "刚刚"
      : mins < 60
        ? mins + "分钟前"
        : mins < 1440
          ? Math.floor(mins / 60) + "小时前"
          : dateLabel(ts);
  }
  function initTheme() {
    try {
      var s = localStorage.getItem("theme");
      document.documentElement.dataset.theme =
        s ||
        (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    } catch (e) {}
  }
  function toggleTheme() {
    var s =
      document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = s;
    try {
      localStorage.setItem("theme", s);
    } catch (e) {}
  }
  async function request(params, signal) {
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, 22000);
    if (signal)
      signal.addEventListener(
        "abort",
        function () {
          controller.abort();
        },
        { once: true },
      );
    try {
      var r = await fetch("/api/news?" + new URLSearchParams(params || {}), {
        signal: controller.signal,
      });
      var d = await r.json();
      if (!r.ok) throw new Error(d.error || "资讯加载失败");
      return d;
    } finally {
      clearTimeout(timer);
    }
  }
  var articles = new Map();
  async function getArticle(id) {
    if (articles.has(String(id))) return articles.get(String(id));
    var d = await request({ id: id });
    articles.set(String(id), d.item);
    return d.item;
  }
  function coverHTML(n, opts) {
    var img = safeUrl(n.image);
    if (!img) return "";
    if (new URL(img).hostname === "img.ithome.com")
      img = "/api/image?id=" + encodeURIComponent(n.id);
    return (
      '<div class="cover"><img class="photo" ' +
      (opts && opts.eager ? 'fetchpriority="high"' : 'loading="lazy"') +
      ' decoding="async" src="' +
      esc(img) +
      '" alt="" onerror="this.parentElement.remove()"></div>'
    );
  }
  function strongStocks(n) {
    return (n.stocks || []).filter(function (s) {
      return s && s.name && s.confidence !== "low";
    });
  }
  function stockTag(s) {
    if (!s || !s.ticker) return "";
    return (
      '<a class="stock-pill" href="stock.html?symbol=' +
      encodeURIComponent(s.ticker) +
      '" title="' +
      esc(s.reason || s.name) +
      '">' +
      esc(s.name) +
      "</a>"
    );
  }
  function storage(key, value) {
    try {
      if (arguments.length > 1)
        localStorage.setItem(key, JSON.stringify(value));
      else return JSON.parse(localStorage.getItem(key) || "null");
    } catch (e) {}
    return null;
  }
  function bookmarks() {
    return storage("aid-bookmarks") || [];
  }
  function toggleBookmark(n) {
    var list = bookmarks();
    var exists = list.some(function (x) {
      return x.id === n.id;
    });
    list = list.filter(function (x) {
      return x.id !== n.id;
    });
    if (!exists)
      list.unshift({
        id: n.id,
        title: n.title,
        summary: n.summary,
        category: n.category,
        source: n.source,
        ts: n.ts,
      });
    storage("aid-bookmarks", list.slice(0, 300));
    return !exists;
  }
  function isBookmarked(id) {
    return bookmarks().some(function (n) {
      return n.id === id;
    });
  }
  function markRead(id) {
    var list = storage("aid-read") || [];
    if (list.indexOf(id) < 0) list.push(id);
    storage("aid-read", list.slice(-1500));
  }
  function isRead(id) {
    return (storage("aid-read") || []).indexOf(id) >= 0;
  }

  var busy = false,
    seed = null,
    history = [],
    controller = null,
    lastQuestion = "",
    lastFocus = null;
  function markdown(el, text) {
    if (global.marked && global.DOMPurify) {
      el.innerHTML = DOMPurify.sanitize(marked.parse(text), {
        FORBID_TAGS: ["img", "style", "iframe", "form", "input"],
      });
      el.querySelectorAll("a").forEach(function (a) {
        if (!safeUrl(a.getAttribute("href"))) a.removeAttribute("href");
        else {
          a.target = "_blank";
          a.rel = "noopener noreferrer";
        }
      });
    } else el.textContent = text;
  }
  function addMsg(cls, text) {
    var d = document.createElement("div");
    d.className = "chat-msg " + cls;
    d.textContent = text;
    document.getElementById("chatMsgs").appendChild(d);
    return d;
  }
  function scrollChat() {
    var box = document.getElementById("chatMsgs");
    box.scrollTop = box.scrollHeight;
  }
  function resetChat() {
    if (controller) controller.abort();
    history = [];
    document.getElementById("chatMsgs").replaceChildren();
    lastQuestion = "";
    document.getElementById("chatRetry").hidden = true;
  }
  function ensureChatUI() {
    if (document.getElementById("chatPanel")) return;
    var mask = document.createElement("div");
    mask.id = "chatMask";
    mask.className = "chat-mask";
    var panel = document.createElement("section");
    panel.id = "chatPanel";
    panel.className = "chat-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-labelledby", "chatTitle");
    panel.hidden = true;
    panel.innerHTML =
      '<div class="chat-head"><strong id="chatTitle">问 AI</strong><span id="chatFocus" class="sub"></span><button class="icon-btn" id="chatNew" title="新对话" aria-label="新对话">' +
      icon("rotate-ccw") +
      '</button><button class="icon-btn" id="chatClose" title="关闭" aria-label="关闭">' +
      icon("x") +
      '</button></div><div class="chat-msgs" id="chatMsgs" aria-live="polite"></div><div class="chat-status" id="chatStatus" role="status"></div><button id="chatRetry" class="text-btn" hidden>重试</button><form class="chat-input" id="chatForm"><textarea id="chatInput" rows="2" maxlength="1000" placeholder="问问这篇报道，或今天的科技进展" aria-label="问题"></textarea><button id="chatSend" class="icon-btn send" type="submit" title="发送" aria-label="发送">' +
      icon("arrow-up") +
      '</button><button id="chatStop" class="icon-btn" type="button" title="停止" aria-label="停止" hidden>' +
      icon("square") +
      "</button></form>";
    document.body.append(mask, panel);
    document.getElementById("chatClose").onclick = closeChat;
    mask.onclick = closeChat;
    document.getElementById("chatNew").onclick = resetChat;
    document.getElementById("chatStop").onclick = function () {
      controller && controller.abort();
    };
    document.getElementById("chatRetry").onclick = function () {
      sendChat(lastQuestion);
    };
    document.getElementById("chatForm").onsubmit = function (e) {
      e.preventDefault();
      sendChat();
    };
    document.getElementById("chatInput").onkeydown = function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        sendChat();
      }
    };
    panel.onkeydown = function (e) {
      if (e.key === "Escape") closeChat();
      if (e.key === "Tab") {
        var focusable = Array.from(
          panel.querySelectorAll("button,textarea,a[href]"),
        ).filter(function (n) {
          return !n.hidden && !n.disabled && n.getClientRects().length;
        });
        var first = focusable[0],
          last = focusable.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    function viewport() {
      if (global.visualViewport) {
        panel.style.bottom =
          Math.max(
            0,
            innerHeight - visualViewport.height - visualViewport.offsetTop,
          ) + "px";
        panel.style.maxHeight =
          Math.max(180, visualViewport.height - 12) + "px";
      }
    }
    if (global.visualViewport) {
      visualViewport.addEventListener("resize", viewport);
      visualViewport.addEventListener("scroll", viewport);
    }
  }
  async function sendChat(retry) {
    if (busy) return;
    var input = document.getElementById("chatInput");
    var q = retry || input.value.trim();
    if (!q) return;
    var preceding = history.slice();
    lastQuestion = q;
    if (!retry) addMsg("me", q);
    input.value = "";
    busy = true;
    controller = new AbortController();
    document.getElementById("chatSend").hidden = true;
    document.getElementById("chatStop").hidden = false;
    document.getElementById("chatRetry").hidden = true;
    var status = document.getElementById("chatStatus");
    status.textContent = "正在连接";
    var reply = addMsg("ai", "");
    var answer = "",
      completed = false;
    try {
      var headers = {
        "content-type": "application/json",
        accept: "text/event-stream",
      };
      try {
        var token = localStorage.getItem("chat_token");
        if (token) headers["x-chat-token"] = token;
      } catch (e) {}
      var r = await fetch("/api/chat", {
        method: "POST",
        headers: headers,
        signal: controller.signal,
        body: JSON.stringify({
          question: q,
          focusId: seed && seed.id,
          history: preceding,
        }),
      });
      if (!r.ok) {
        var error = await r.json();
        throw new Error(error.error || "请求失败");
      }
      if (
        !String(r.headers.get("content-type")).includes("text/event-stream")
      ) {
        var data = await r.json();
        if (!data.answer) throw new Error(data.error || "未收到回答");
        answer = data.answer;
        completed = true;
        markdown(reply, answer);
      } else {
        var reader = r.body.getReader(),
          decoder = new TextDecoder(),
          buffer = "";
        function event(chunk) {
          var lines = chunk.split("\n");
          var type = (
            lines.find(function (l) {
              return l.startsWith("event:");
            }) || ""
          )
            .slice(6)
            .trim();
          var payload = lines
            .filter(function (l) {
              return l.startsWith("data:");
            })
            .map(function (l) {
              return l.slice(5).trim();
            })
            .join("\n");
          if (!payload) return;
          var d = JSON.parse(payload);
          if (type === "status") status.textContent = d.text;
          if (type === "delta") {
            answer += d.text;
            markdown(reply, answer);
            scrollChat();
          }
          if (type === "error") throw new Error(d.error);
          if (type === "done") {
            completed = true;
            answer = d.answer;
            markdown(reply, answer);
          }
        }
        while (true) {
          var piece = await reader.read();
          if (piece.done) break;
          buffer += decoder.decode(piece.value, { stream: true });
          buffer = buffer.replace(/\r\n/g, "\n");
          var pos;
          while ((pos = buffer.indexOf("\n\n")) >= 0) {
            event(buffer.slice(0, pos));
            buffer = buffer.slice(pos + 2);
          }
        }
        if (buffer.trim()) event(buffer);
        if (!completed) throw new Error("连接中断，请重试。");
      }
      history = preceding
        .concat([
          { role: "user", content: q },
          { role: "assistant", content: answer },
        ])
        .slice(-8);
      status.textContent = "";
    } catch (e) {
      if (!answer) reply.remove();
      status.textContent = e.name === "AbortError" ? "已停止" : e.message;
      document.getElementById("chatRetry").hidden = false;
    } finally {
      busy = false;
      controller = null;
      document.getElementById("chatSend").hidden = false;
      document.getElementById("chatStop").hidden = true;
      scrollChat();
    }
  }
  function openChat(opts) {
    ensureChatUI();
    opts = opts || {};
    var next = opts.focus || null;
    if (seed && next && seed.id !== next.id) resetChat();
    seed = next;
    document.getElementById("chatFocus").textContent = seed ? seed.title : "";
    lastFocus = document.activeElement;
    var panel = document.getElementById("chatPanel");
    panel.hidden = false;
    document.body.classList.add("chat-open");
    document.getElementById("chatMask").classList.add("open");
    requestAnimationFrame(function () {
      panel.classList.add("open");
      document.getElementById("chatInput").focus();
    });
  }
  function closeChat() {
    document.getElementById("chatPanel").classList.remove("open");
    document.getElementById("chatPanel").hidden = true;
    document.getElementById("chatMask").classList.remove("open");
    document.body.classList.remove("chat-open");
    lastFocus && lastFocus.focus();
  }
  global.AID = {
    esc: esc,
    safeUrl: safeUrl,
    icon: icon,
    relTime: relTime,
    dateLabel: dateLabel,
    catOrder: cats,
    initTheme: initTheme,
    toggleTheme: toggleTheme,
    request: request,
    getArticle: getArticle,
    coverHTML: coverHTML,
    strongStocks: strongStocks,
    stockTag: stockTag,
    bookmarks: bookmarks,
    toggleBookmark: toggleBookmark,
    isBookmarked: isBookmarked,
    markRead: markRead,
    isRead: isRead,
    openChat: openChat,
    bindChatControls: ensureChatUI,
    getParam: function (key) {
      return new URLSearchParams(location.search).get(key);
    },
    loadNews: function (_, cb) {
      request({ limit: 60 })
        .then(function (d) {
          cb(d.items, d.digest);
        })
        .catch(function () {
          cb([], null);
        });
    },
    loadBody: function (id) {
      return getArticle(id).then(function (n) {
        return n.body || "";
      });
    },
    findNewsById: function (_, id, cb) {
      getArticle(id)
        .then(cb)
        .catch(function () {
          cb(null);
        });
    },
  };
  initTheme();
})(window);
