(function () {
  var A = window.AID,
    items = [],
    category = "",
    query = "",
    offset = 0,
    next = null,
    busy = false,
    version = "",
    saved = false,
    archive = false,
    source = "",
    from = "",
    to = "",
    viewData = null,
    feedMeta = null,
    serial = 0;
  var feed = document.getElementById("feed"),
    more = document.getElementById("more");
  var $ = function (id) {
    return document.getElementById(id);
  };
  function readLocation() {
    var p = new URLSearchParams(location.search);
    category = p.get("category") || "";
    query = p.get("q") || "";
    source = p.get("source") || "";
    from = p.get("from") || "";
    to = p.get("to") || "";
    archive = p.get("archive") === "1";
    saved = p.get("saved") === "1";
    $("searchInput").value = query;
    $("fromFilter").value = from;
    $("toFilter").value = to;
    $("sourceFilter").value = source;
    $("searchBar").hidden = !(p.get("search") === "1" || query || source || from || to);
  }
  function saveView() {
    var url = new URL(location.href);
    var values = { category: category, q: query, source: source, from: from, to: to,
      archive: archive ? "1" : "", saved: saved ? "1" : "",
      search: $("searchBar").hidden ? "" : "1" };
    Object.keys(values).forEach(function (key) {
      if (values[key]) url.searchParams.set(key, values[key]);
      else url.searchParams.delete(key);
    });
    var state = Object.assign({}, history.state, { aidFeed: null });
    if (viewData) state.aidFeed = {
      url: url.href, data: Object.assign({}, viewData, { items: items, nextOffset: next }),
      offset: offset, scrollY: window.scrollY,
    };
    try {
      history.replaceState(state, "", url);
    } catch (e) {
      // Filters remain shareable even when a long list exceeds the history-state quota.
      history.replaceState({ aidFeed: null }, "", url);
    }
  }
  function restoreView() {
    readLocation();
    var snapshot = history.state && history.state.aidFeed;
    if (snapshot && snapshot.url === location.href && snapshot.data) {
      serial++;
      busy = false;
      offset = snapshot.offset || 0;
      applyData(snapshot.data, false);
      more.disabled = false;
      $("refreshBtn").disabled = false;
      requestAnimationFrame(function () {
        window.scrollTo(0, snapshot.scrollY || 0);
      });
    } else load(false);
  }
  function itemHTML(n) {
    return (
      '<article class="item' +
      (A.isRead(n.id) ? " read" : "") +
      '"><div class="item-body"><a class="item-title" href="detail.html?id=' +
      encodeURIComponent(n.id) +
      '">' +
      A.esc(n.title) +
      '</a><p class="item-summary">' +
      A.esc(n.summary) +
      '</p><div class="item-meta"><span class="chip">' +
      A.esc(n.category) +
      "</span><span>" +
      A.esc(n.source) +
      '</span><time datetime="' +
      A.esc(n.ts) +
      '" title="' +
      A.esc(A.dateLabel(n.ts)) +
      '">' +
      A.relTime(n.ts) +
      "</time>" +
      A.strongStocks(n).slice(0, 1).map(A.stockTag).join("") +
      "</div></div>" +
      A.coverHTML(n) +
      '<button class="save-btn icon-btn' +
      (A.isBookmarked(n.id) ? " selected" : "") +
      '" data-id="' +
      n.id +
      '" title="收藏" aria-label="收藏" aria-pressed="' +
      A.isBookmarked(n.id) +
      '">' +
      A.icon("bookmark") +
      "</button></article>"
    );
  }
  function render() {
    feed.innerHTML = items.length
      ? items.map(itemHTML).join("")
      : '<div class="empty">没有匹配的资讯</div>';
    more.hidden = next == null;
    feed.querySelectorAll(".save-btn").forEach(function (b) {
      b.onclick = function () {
        var n = items.find(function (n) {
          return n.id === b.dataset.id;
        });
        var selected = A.toggleBookmark(n);
        b.classList.toggle("selected", selected);
        b.setAttribute("aria-pressed", selected);
        if (saved) {
          items = A.bookmarks();
          $("resultCount").textContent = items.length + " 条";
          render();
        }
        saveView();
      };
    });
  }
  function showStatus(s) {
    if (!s) return;
    var health = A.updateHealth(s);
    $("updateStatus").textContent =
      health.label +
      " · " +
      (s.checkedAt ? A.dateLabel(s.checkedAt) : "暂无记录") +
      " · 本轮新增 " +
      (s.added || 0) +
      " 条";
    $("updateStatus").classList.toggle("warning", health.state !== "ok");
    $("updateStatus").dataset.state = health.state;
    var failed = (s.sources || []).filter(function (x) {
      return !x.ok;
    });
    $("updateDetails").innerHTML =
      "<p>最后检查 <strong>" +
      A.dateLabel(s.checkedAt) +
      "</strong></p><p>最后入库 <strong>" +
      (A.dateLabel(s.lastIngestedAt) || "暂无记录") +
      "</strong></p><p>最新报道 <strong>" +
      A.dateLabel(s.latestPublishedAt) +
      "</strong></p><p>待重试 <strong>" +
      (s.pendingRetries || 0) +
      "</strong></p><p" + (s.exhaustedRetries ? ' class="warning"' : "") +
      ">重试耗尽 <strong>" + (s.exhaustedRetries || 0) + "</strong></p>" +
      (s.stale ? '<p class="warning">当前使用缓存数据</p>' : "") +
      (s.error ? '<p class="warning">更新错误：' + A.esc(s.error) + "</p>" : "") +
      (failed.length
        ? '<p class="warning">来源异常：' +
          failed
            .map(function (x) {
              return A.esc(x.source) + (x.error ? "（" + A.esc(x.error) + "）" : "");
            })
            .join("、") +
          "</p>"
        : "");
    $("updateInfo").innerHTML = $("updateDetails").innerHTML;
  }
  function renderDigest(d) {
    $("digest").innerHTML =
      d && d.text
        ? '<details class="digest"><summary>今日综述 <span>AI 整理</span>' +
          A.icon("chevron-down") +
          "</summary><p>" +
          A.esc(d.text) +
          "</p></details>"
        : "";
    var ids = (d && d.highlights) || [];
    Promise.all(
      ids.slice(0, 4).map(function (id) {
        return A.getArticle(id).catch(function () {
          return null;
        });
      }),
    ).then(function (ns) {
      $("highlights").innerHTML = ns
        .filter(Boolean)
        .map(function (n) {
          return (
            '<a class="highlight" href="detail.html?id=' +
            n.id +
            '"><span class="chip">' +
            A.esc(n.category) +
            "</span><strong>" +
            A.esc(n.title) +
            "</strong><small>" +
            A.esc(n.source) +
            "</small></a>"
          );
        })
        .join("");
    });
  }
  function applyData(d, append) {
    feedMeta = d;
    version = d.version;
    items = saved ? A.bookmarks() : (append ? items.concat(d.items) : d.items);
    next = saved ? null : d.nextOffset;
    viewData = d;
    $("feedTitle").textContent = saved ? "我的收藏" : query ? "搜索结果" :
      category || (d.scope === "archive" ? "历史资讯" : "最新资讯");
    $("resultCount").textContent = saved ? items.length + " 条" : d.total + " 条" +
      (d.scope === "recent" ? " · 归档 " + d.categoryTotal + " 条" : "");
    $("scopeFilter").hidden = Boolean(saved || query || source || from || to);
    $("scopeFilter").querySelectorAll("button").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.archive === (archive ? "1" : "0")));
    });
    $("savedBtn").classList.toggle("active", saved);
    showStatus(d.status);
    render();
    if (!append) {
      renderDigest(d.digest);
      $("newNews").hidden = true;
    }
    if (!$("tabs").children.length) {
      $("tabs").innerHTML = ["", ...A.catOrder]
        .filter(function (c) { return !c || d.categories[c]; })
        .map(function (c) {
          return '<button class="tab" data-cat="' + A.esc(c) + '">' + A.esc(c || "全部") + "</button>";
        }).join("");
      $("tabs").querySelectorAll("button").forEach(function (button) {
        button.onclick = function () {
          saved = false;
          category = button.dataset.cat;
          load(false);
        };
      });
    }
    $("tabs").querySelectorAll("button").forEach(function (button) {
      button.classList.toggle("active", !saved && button.dataset.cat === category);
    });
    if ($("sourceFilter").options.length === 1)
      Object.keys(d.sources || {}).sort().forEach(function (name) {
        var option = document.createElement("option");
        option.value = option.textContent = name;
        $("sourceFilter").appendChild(option);
      });
    $("sourceFilter").value = source;
  }
  async function load(append) {
    var ticket = ++serial;
    busy = true;
    more.disabled = true;
    $("refreshBtn").disabled = true;
    if (!append) {
      viewData = null;
      offset = 0;
      items = [];
      feed.innerHTML = '<div class="empty">加载中…</div>';
    }
    saveView();
    try {
      if (saved) {
        applyData(feedMeta || {
          items: [], nextOffset: null, version: "", sources: {},
          categories: Object.fromEntries(A.catOrder.map(function (name) { return [name, 1]; })),
        }, false);
        saveView();
        return;
      }
      var params = { limit: 40, offset: offset };
      if (category) params.category = category;
      if (query) params.q = query;
      if (archive) params.archive = "1";
      if (source) params.source = source;
      if (from) params.from = from;
      if (to) params.to = to;
      var d = await A.request(params);
      if (ticket !== serial) return;
      applyData(d, append);
      saveView();
    } catch (e) {
      if (ticket === serial) {
        feed.innerHTML =
          '<div class="empty">' +
          A.esc(e.message) +
          '<br><button class="text-btn" id="retryNews">重试</button></div>';
        $("retryNews").onclick = function () {
          load(false);
        };
      }
    } finally {
      if (ticket === serial) {
        busy = false;
        more.disabled = false;
        $("refreshBtn").disabled = false;
      }
    }
  }
  more.onclick = function () {
    if (!busy && next != null) {
      offset = next;
      load(true);
    }
  };
  $("refreshBtn").onclick = function () {
    saved = false;
    load(false);
  };
  $("newNews").onclick = function () {
    saved = false;
    load(false);
  };
  $("updateStatus").onclick = function () {
    $("updateInfo").hidden = !$("updateInfo").hidden;
    this.setAttribute("aria-expanded", !$("updateInfo").hidden);
  };
  $("themeBtn").onclick = A.toggleTheme;
  $("chatBtn").onclick = function () {
    A.openChat();
  };
  $("savedBtn").onclick = function () {
    saved = true;
    load(false);
  };
  $("searchBtn").onclick = function () {
    $("searchBar").hidden = !$("searchBar").hidden;
    if (!$("searchBar").hidden) $("searchInput").focus();
    saveView();
  };
  $("searchClear").onclick = function () {
    $("searchBar").hidden = true;
    $("searchInput").value = "";
    $("sourceFilter").value = "";
    $("fromFilter").value = "";
    $("toFilter").value = "";
    query = "";
    source = from = to = "";
    load(false);
  };
  var timer;
  $("searchInput").oninput = function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      saved = false;
      query = $("searchInput").value.trim();
      load(false);
    }, 300);
  };
  ["sourceFilter", "fromFilter", "toFilter"].forEach(function (id) {
    $(id).onchange = function () {
      saved = false;
      source = $("sourceFilter").value;
      from = $("fromFilter").value;
      to = $("toFilter").value;
      load(false);
    };
  });
  $("scopeFilter").querySelectorAll("button").forEach(function (button) {
    button.onclick = function () {
      archive = button.dataset.archive === "1";
      load(false);
    };
  });
  async function poll() {
    if (document.hidden) return;
    try {
      var s = await A.request({ status: 1 });
      if (viewData) viewData.status = s;
      showStatus(s);
      if (version && s.version !== version) {
        $("newNews").textContent = "有新资讯，点击更新";
        $("newNews").hidden = false;
      }
    } catch (e) {}
  }
  setInterval(poll, 120000);
  document.addEventListener("visibilitychange", poll);
  history.scrollRestoration = "manual";
  window.addEventListener("pagehide", saveView);
  window.addEventListener("popstate", restoreView);
  window.addEventListener("pageshow", function (event) {
    if (event.persisted) restoreView();
  });
  document.addEventListener("click", function (event) {
    if (event.target.closest("a[href]")) saveView();
  }, true);
  restoreView();
  if (A.getParam("chat") === "1") A.openChat();
})();
