# 前沿科技日报 (ai-daily-v3)

AI 驱动的中文科技日报。约每 10 分钟抓取中外科技 RSS/AIHOT 源 → Kimi 翻译/摘要/分类 + 推断关联标的 → 数据入库,每 30 分钟随站点一起部署。点新闻里的标的可看实时行情。

线上:https://ai-daily-v3.vercel.app

## 它自动做什么

GitHub Action(`.github/workflows/update-news.yml`,每 10 分钟)：

```
fetch_rss.py 抓多路中外科技 RSS/AIHOT 源
  → enrich_news.py:
      · 按 URL 对 seen_urls.json 去重,只处理没见过的新条目
      · 每条调 Kimi(kimi-for-coding)→ 中文标题/摘要/正文 + 分类 + 标签 + 关联标的
      · 非科技/科学/前沿产业/地缘科技相关内容直接跳过
      · 单次最多富化 50 条(CAP);累计并入历史、带 ts 时间戳按时间倒序;每个板块各留最新 KEEP=2000 条(到顶才淘汰该板块最旧)
      · 生成今日综述 digest
      · 写 data/ 下的拆分 JSON + sitemap.xml
  → 数据 <10 条则放弃(防覆盖)
  → 有新数据才 git push
```

`.github/workflows/deploy-site.yml` 每 30 分钟把最新代码 + 数据一起 `vercel --prod` 部署(数据与站点同源,浏览器走 ETag 协商缓存;线上新闻最多滞后约 30 分钟)。无新条目的批次:不改文件、不提交。

## 数据文件(由管线生成,前端直读)

| 文件 | 作用 |
|---|---|
| `data/index.json` | 全量瘦索引(无正文):列表、搜索、问AI 用 |
| `data/index-hot.json` | 最新 400 条的热索引:首屏先渲染,再后台补全量 |
| `data/items/<xx>.json` | 按 id 前 2 位分片的完整条目(含正文):详情页只取所在分片 |
| `data/tickers.json` | 当日全部关联标的:行情页直读,无需下载新闻数据 |
| `sitemap.xml` | 全部详情页 URL,供搜索引擎抓取 |
| `seen_urls.json` | 去重用的已见 URL 清单(最多 5000) |

## 代码文件说明

| 文件 | 作用 |
|---|---|
| `index.html` | 首页:今日综述卡 + 头条 + 热榜 + 分类信息流 + 搜索 |
| `detail.html` | 详情页:AI 中文正文 + 关联标的 |
| `stock.html` | 行情页:点标的看实时行情;无参时汇总当日全部标的 |
| `assets/theme.css` | 设计系统(含暗色模式) |
| `assets/app.js` | 前端共享逻辑(分类封面、数据加载、标的标签等) |
| `fetch_rss.py` | RSS 抓取(纯标准库) |
| `enrich_news.py` | 抓取→去重→Kimi 富化→写数据(管线主程序) |
| `api/quote.js` | Vercel serverless:代理新浪财经取实时行情 |
| `api/chat.js` | Vercel serverless:AI 对话(服务端召回站内资讯,可切 Qwen/Kimi) |

## 怎么改

- **加/删数据源**:`fetch_rss.py` 的 `FEEDS` 列表(每项 `(来源名, RSS地址, 默认分类)`)和 `fetch_aihot_items()`。每源取多少条改 `PER_FEED` / `AIHOT_TAKE`。
- **单次富化上限 / 每板块累计上限 / 热索引条数**:`enrich_news.py` 顶部 `CAP`(默认 50)、`KEEP`(默认 2000,**按板块**)、`HOT`(默认 400);也可用环境变量 `AID_CAP` / `AID_KEEP` / `AID_HOT` 覆盖(如一次性补量:`AID_CAP=200 python3 enrich_news.py`)。
- **更新频率**:`.github/workflows/update-news.yml` 的 `cron`;**部署频率**:`.github/workflows/deploy-site.yml` 的 `cron`(注意 Vercel Hobby 每日部署上限 100)。
- **新闻富化模型**:`enrich_news.py` 默认 `ENRICH_PROVIDER=kimi`,使用 `KIMI_KEY` / `KIMI_MODEL=kimi-for-coding`;如需回退可设 `ENRICH_PROVIDER=qwen`。
- **问 AI 模型**:`api/chat.js` 生产默认 Kimi;Vercel 设 `CHAT_PROVIDER=qwen` 可回退 Qwen。
- **分类与封面配色**:`assets/app.js` 的 `CATS`;`enrich_news.py` 的 `CATEGORIES`(两处分类要一致)。
- **站点域名**(用于 sitemap):环境变量 `AID_SITE_BASE`,默认 `https://ai-daily-v3.vercel.app`。

## 分类体系

一级分类控制在前沿科技主线内:

`人工智能`、`AI 基础设施`、`半导体与先进制造`、`机器人`、`商业航天`、`生物医药`、`量子科技`、`未来能源`、`新材料`、`脑机接口`、`网络安全`、`消费电子`、`地缘科技`。

`地缘科技`只收技术制裁、出口管制、国防科技、关键矿产、科技政策、供应链安全等科技相关议题,不收普通国际政治、体育、灾害和社会新闻。

## 实时行情

`stock.html?symbol=NVDA` → 调 `/api/quote?symbol=NVDA,0700.HK,600519.SH`(支持批量)。
- 数据源:新浪财经 `hq.sinajs.cn`(免费、无 key),serverless 内 GBK 解码、分 US/HK/CN 解析。
- 代码格式:美股直接代码(NVDA);港股 `0700.HK`;A股 `600519.SH` / `000001.SZ`。
- **时效**:A股/港股盘中接近实时,美股约延迟 15 分钟。新浪为非官方接口,若失效需换源(腾讯 `qt.gtimg.cn` / Yahoo,或接已登录的 Longbridge CLI)。
- 红涨绿跌(中国习惯)。

## AI 对话(问AI)

底栏「问AI」打开对话面板 → 前端只 POST `{ question }` 给 `/api/chat` → 服务端从 `data/index.json`(部署包内,随数据一起更新)召回相关资讯;站内覆盖不足时才做网页检索,再交给模型回答。
- 默认:`CHAT_PROVIDER=kimi`,走 Kimi Coding Plan,使用 `KIMI_KEY`,模型 `KIMI_MODEL` 默认 `kimi-for-coding`。
- Qwen 回退:`CHAT_PROVIDER=qwen`,使用 `QWEN_KEY`,模型 `QWEN_MODEL` 默认 `qwen3.7-max`。
- 如使用普通 Moonshot OpenAI-compatible API,设 `KIMI_API_STYLE=openai`、`MOONSHOT_API_KEY`;API base 默认 `https://api.moonshot.ai/v1`,中国区可设 `KIMI_BASE_URL=https://api.moonshot.cn/v1`。
- 防刷:端点默认公开(有限流);在 Vercel 设 `CHAT_TOKEN` 后,请求必须带 `x-chat-token` 头(适合私有部署;注意公开网页无法安全携带该口令)。

## 移动端(App / PWA)

站点已是可安装的 PWA(`manifest.webmanifest` + `sw.js`,支持离线回看),`mobile/` 下另有 Capacitor 原生壳工程(WebView 加载线上站点)。

**iPhone(免上架、零成本,推荐)**:Safari 打开站点 → 分享 → 「添加到主屏幕」,即得全屏、带图标的类 App 体验。

**安卓**:
- 方式一:Chrome 打开站点 → 菜单 → 「安装应用」(PWA)。
- 方式二:直接安装 APK(设置里允许「安装未知应用」)。本地构建:
  ```bash
  cd mobile && npm install && npx cap sync android
  cd android && ./gradlew assembleDebug     # 产物在 app/build/outputs/apk/debug/
  ```
  需要 JDK 17+ 与 Android SDK(`local.properties` 里配 `sdk.dir`)。release 版用自己的 keystore 通过 `-Pandroid.injected.signing.*` 参数签名。

**iOS 原生壳(需要 Mac)**:`cd mobile && npx cap open ios`,Xcode 里用免费 Apple ID 个人签名(Signing & Capabilities → 选自己的 Team),连接 iPhone 直接安装(免开发者年费,签名 7 天有效期,到期重新点一次安装;或用 AltStore 自动续签)。

说明:壳应用加载 `mobile/capacitor.config.json` 里 `server.url` 指向的线上站点,站点更新后 App 内容自动更新,无需重新打包。

## 部署 / Secrets

- GitHub→Vercel 自动部署未接通,由 `deploy-site.yml` 每 30 分钟 `vercel --prod` 部署代码 + 数据。
- 仓库 Secrets(GitHub Actions 用):`KIMI_KEY`、`QWEN_KEY`、`VERCEL_TOKEN`、`VERCEL_ORG_ID`、`VERCEL_PROJECT_ID`。
- Vercel 环境变量(serverless 函数用):`CHAT_PROVIDER=kimi`、`KIMI_KEY`;若回退 Qwen,加 `CHAT_PROVIDER=qwen`、`QWEN_KEY`;若切普通 Moonshot API,加 `CHAT_PROVIDER=kimi`、`KIMI_API_STYLE=openai`、`MOONSHOT_API_KEY`;可选 `CHAT_TOKEN` 防刷。
- 本地手动部署:`npx vercel deploy --prod --token <VERCEL_TOKEN>`。

## 成本

抓取 / 调度(GitHub Action 公开仓库)/ 托管(Vercel)/ RSS / 新浪行情 —— 全免费。
唯一按量计费:Kimi/Qwen 模型调用(每批只富化新条目,无新闻的批次近 0)。

## 已知限制

- 强制每条出利好标的 → 个别关联偏弱(reason 里会点明强弱)。
- 新浪行情非官方接口,稳定性不保证。
- `/api/chat` 默认公开(有限流 + 可选 `CHAT_TOKEN`),被刷仍会烧模型 token。
- 线上新闻随 30 分钟一次的部署更新,比抓取节奏(10 分钟)略有滞后。
- 部分小众分类(机器人/量子科技等)条目偏少,靠累计逐步填充。
