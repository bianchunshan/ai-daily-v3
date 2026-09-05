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
    serial = 0;
  var feed = document.getElementById("feed"),
    more = document.getElementById("more");
  var $ = function (id) {
    return document.getElementById(id);
  };
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
          render();
        }
      };
    });
  }
  function showStatus(s) {
    if (!s) return;
    var age = Date.now() - Date.parse(s.checkedAt);
    var healthy = s.state === "ok" && age < 25 * 60000 && !s.stale;
    $("updateStatus").textContent =
      (healthy ? "检查正常" : "更新需检查") +
      " · " +
      (s.checkedAt ? A.dateLabel(s.checkedAt) : "暂无记录") +
      " · 本轮新增 " +
      (s.added || 0) +
      " 条";
    $("updateStatus").classList.toggle("warning", !healthy);
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
      "</strong></p>" +
      (failed.length
        ? '<p class="warning">来源异常：' +
          failed
            .map(function (x) {
              return A.esc(x.source);
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
  async function load(append) {
    var ticket = ++serial;
    busy = true;
    more.disabled = true;
    $("refreshBtn").disabled = true;
    if (!append) {
      offset = 0;
      items = [];
      feed.innerHTML = '<div class="empty">加载中…</div>';
    }
    try {
      if (saved) {
        items = A.bookmarks();
        next = null;
        $("feedTitle").textContent = "我的收藏";
        $("resultCount").textContent = items.length + " 条";
        render();
        return;
      }
      var params = { limit: 40, offset: offset };
      if (category) params.category = category;
      if (query) params.q = query;
      if ($("sourceFilter").value) params.source = $("sourceFilter").value;
      if ($("fromFilter").value) params.from = $("fromFilter").value;
      if ($("toFilter").value) params.to = $("toFilter").value;
      var d = await A.request(params);
      if (ticket !== serial) return;
      version = d.version;
      items = append ? items.concat(d.items) : d.items;
      next = d.nextOffset;
      $("feedTitle").textContent = query ? "搜索结果" : category || "最新资讯";
      $("resultCount").textContent = d.total + " 条";
      showStatus(d.status);
      render();
      if (!append) {
        renderDigest(d.digest);
        $("newNews").hidden = true;
      }
      if (!$("tabs").children.length) {
        $("tabs").innerHTML = ["", ...A.catOrder]
          .filter(function (c) {
            return !c || d.categories[c];
          })
          .map(function (c) {
            return (
              '<button class="tab' +
              (c === category ? " active" : "") +
              '" data-cat="' +
              A.esc(c) +
              '">' +
              A.esc(c || "全部") +
              "</button>"
            );
          })
          .join("");
        $("tabs")
          .querySelectorAll("button")
          .forEach(function (b) {
            b.onclick = function () {
              saved = false;
              category = b.dataset.cat;
              $("tabs")
                .querySelectorAll("button")
                .forEach(function (x) {
                  x.classList.toggle("active", x === b);
                });
              load(false);
            };
          });
      }
      if ($("sourceFilter").options.length === 1)
        Object.keys(d.sources || {})
          .sort()
          .forEach(function (s) {
            var option = document.createElement("option");
            option.value = s;
            option.textContent = s;
            $("sourceFilter").appendChild(option);
          });
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
  };
  $("searchClear").onclick = function () {
    $("searchBar").hidden = true;
    $("searchInput").value = "";
    $("sourceFilter").value = "";
    $("fromFilter").value = "";
    $("toFilter").value = "";
    query = "";
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
      load(false);
    };
  });
  async function poll() {
    if (document.hidden) return;
    try {
      var s = await A.request({ status: 1 });
      showStatus(s);
      if (version && s.version !== version) {
        $("newNews").textContent = "有新资讯，点击更新";
        $("newNews").hidden = false;
      }
    } catch (e) {}
  }
  setInterval(poll, 120000);
  document.addEventListener("visibilitychange", poll);
  load(false);
  if (A.getParam("chat") === "1") A.openChat();
})();
