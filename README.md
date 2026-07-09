# 前沿科技日报 (ai-daily-v3)

AI 驱动的中文科技日报。约每 10 分钟抓取中外科技 RSS/AIHOT 源 → Kimi 翻译/摘要/分类 + 推断关联标的 → 自动部署。点新闻里的标的可看实时行情。

线上:https://ai-daily-v3.vercel.app

## 它自动做什么

GitHub Action(`.github/workflows/update-news.yml`,`cron: 7,17,27,37,47,57 * * * *`)：

```
fetch_rss.py 抓多路中外科技 RSS/AIHOT 源
  → enrich_news.py:
      · 按 URL 对 seen_urls.json 去重,只处理没见过的新条目
      · 每条调 Kimi(kimi-for-coding)→ 中文标题/摘要/正文 + 分类 + 标签 + 关联标的
      · 非科技/科学/前沿产业/地缘科技相关内容直接跳过
      · 单次最多富化 50 条(CAP);累计并入历史、带 ts 时间戳按时间倒序;每个板块各留最新 KEEP=2000 条(到顶才淘汰该板块最旧)
      · 生成今日综述 newsDigest
      · 写全量 news_data_latest.js + 前端轻量 news_data_list.js + news_bodies.json + news_chat_index.json
  → 抓到 <10 条则放弃(防覆盖)
  → 有新数据才 git push(前端从 GitHub raw 读最新数据;站点壳由 deploy-site 低频部署)
```

无新条目的批次:不改文件、不部署。

## 文件说明

| 文件 | 作用 |
|---|---|
| `index.html` | 首页:今日综述卡 + 头条 + 推荐指数 + 分类信息流 + 内联搜索 |
| `detail.html` | 详情页:按需加载正文 + 关联标的 + 问AI |
| `stock.html` | 行情页:分批加载、按涨跌幅排序、市场筛选 |
| `assets/theme.css` | 设计系统(含暗色模式) |
| `assets/app.js` | 前端共享逻辑(封面、加载列表/正文、标的标签、问AI面板) |
| `fetch_rss.py` | RSS 抓取(纯标准库) |
| `enrich_news.py` | 抓取→去重→Kimi 富化→写拆分数据(管线主程序) |
| `api/quote.js` | Vercel serverless:代理新浪财经取实时行情 |
| `api/chat.js` | Vercel serverless:AI 对话(读轻量索引召回,按需网页检索) |
| `news_data_list.js` | **前端主数据**(无正文,近 14 天/最多 800 条);线上从 GitHub raw 拉取 |
| `news_bodies.json` | 详情页按需加载的正文映射 `{id: body}` |
| `news_chat_index.json` | 问AI 服务端召回索引 |
| `news_data_latest.js` | 全量归档(管线累计 + 兜底) |
| `seen_urls.json` | 去重用的已见 URL 清单(最多 5000) |
| `vercel.json` | 静态资源缓存策略 |

## 怎么改

- **加/删数据源**:`fetch_rss.py` 的 `FEEDS` 列表(每项 `(来源名, RSS地址, 默认分类)`)和 `fetch_aihot_items()`。每源取多少条改 `PER_FEED` / `AIHOT_TAKE`。
- **单次富化上限 / 每板块累计上限**:`enrich_news.py` 顶部 `CAP`(默认 50)、`KEEP`(默认 2000,**按板块**);也可用环境变量 `AID_CAP` / `AID_KEEP` 覆盖。
- **前端列表窗口**:`AID_FRONTEND_DAYS`(默认 14)、`AID_FRONTEND_MAX`(默认 800)、`AID_CHAT_INDEX_MAX`(默认 1500)。
- **更新频率**:`.github/workflows/update-news.yml` 的 `cron`。
- **新闻富化模型**:`enrich_news.py` 默认 `ENRICH_PROVIDER=kimi`,使用 `KIMI_KEY` / `KIMI_MODEL=kimi-for-coding`;如需回退可设 `ENRICH_PROVIDER=qwen`。
- **问 AI 模型**:`api/chat.js` 生产默认 Kimi;Vercel 设 `CHAT_PROVIDER=qwen` 可回退 Qwen。
- **问 AI 口令**(可选):Vercel 设 `CHAT_TOKEN=你的口令`,前端可在控制台执行 `localStorage.setItem('chat_token','你的口令')`。
- **分类与封面配色**:`assets/app.js` 的 `CATS`;`enrich_news.py` 的 `CATEGORIES`(两处分类要一致)。

## 分类体系

一级分类控制在前沿科技主线内:

`人工智能`、`AI 基础设施`、`半导体与先进制造`、`机器人`、`商业航天`、`生物医药`、`量子科技`、`未来能源`、`新材料`、`脑机接口`、`网络安全`、`消费电子`、`地缘科技`。

`地缘科技`只收技术制裁、出口管制、国防科技、关键矿产、科技政策、供应链安全等科技相关议题,不收普通国际政治、体育、灾害和社会新闻。

## 实时行情

`stock.html?symbol=NVDA` → 调 `/api/quote?symbol=NVDA,0700.HK,600519.SH`(支持批量)。
- 数据源:新浪财经 `hq.sinajs.cn`(免费、无 key),serverless 内 GBK 解码、分 US/HK/CN 解析。
- 代码格式:美股直接代码(NVDA);港股 `0700.HK`;A股 `600519.SH` / `000001.SZ`。
- **时效**:A股/港股盘中接近实时,美股约延迟 15 分钟。新浪为非官方接口,若失效需换源。
- 红涨绿跌(中国习惯)。列表默认隐藏 `confidence: low` 的弱关联标的。

## AI 对话(问AI)

底栏「问AI」或详情「基于这篇提问」→ 前端 POST `{ question, focusId? }` 给 `/api/chat` → 服务端从 `news_chat_index.json` 召回,必要时做网页检索,再交给模型回答。
- 默认:`CHAT_PROVIDER=kimi`,走 Kimi Coding Plan。
- Qwen 回退:`CHAT_PROVIDER=qwen` + `QWEN_KEY`。
- 可选鉴权:`CHAT_TOKEN`;请求头需带 `x-chat-token`。
- ⚠️ 未设 `CHAT_TOKEN` 时端点公开,已有限流,仍会消耗模型 token。

## 部署 / Secrets

- 新闻数据:Action 推到 GitHub 后,前端/问AI 从 `raw.githubusercontent.com` 拉 `news_data_list.js` / `news_bodies.json` / `news_chat_index.json`。
- 站点壳:`.github/workflows/deploy-site.yml` 低频/手动 `vercel --prod`(main 的 git 自动部署已关)。
- 仓库 Secrets:`KIMI_KEY`、`QWEN_KEY`、`VERCEL_TOKEN`、`VERCEL_ORG_ID`、`VERCEL_PROJECT_ID`。
- Vercel 环境变量:`CHAT_PROVIDER=kimi`、`KIMI_KEY`;可选 `CHAT_TOKEN`。
- 本地手动部署:`npx vercel deploy --prod --token <VERCEL_TOKEN>`。

## 成本

抓取 / 调度(GitHub Action 公开仓库)/ 托管(Vercel)/ RSS / 新浪行情 —— 全免费。
唯一按量计费:Kimi/Qwen 模型调用(每批只富化新条目,无新闻的批次近 0)。

## 已知限制

- 强制每条出利好标的 → 个别关联偏弱(前端默认隐藏 low,详情可展开)。
- 新浪行情非官方接口,稳定性不保证。
- `/api/chat` 建议配置 `CHAT_TOKEN` 防刷。
- 部分小众分类条目偏少,靠累计逐步填充。
