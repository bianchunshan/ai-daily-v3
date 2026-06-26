# 前沿科技日报 (ai-daily-v3)

AI 驱动的中文科技日报。每小时抓取中外科技 RSS → Qwen 翻译/摘要/分类 + 推断利好标的 → 自动部署。点新闻里的标的可看实时行情。

线上:https://ai-daily-v3.vercel.app

## 它每小时自动做什么

GitHub Action(`.github/workflows/update-news.yml`,`cron: 17 * * * *`)：

```
fetch_rss.py 抓多路中外科技 RSS
  → enrich_news.py:
      · 按 URL 对 seen_urls.json 去重,只处理没见过的新条目
      · 每条调 Qwen(qwen3.7-max)→ 中文标题/摘要/正文 + 分类 + 标签 + 关联标的
      · 单次最多富化 50 条(CAP);累计并入历史、带 ts 时间戳按时间倒序;每个板块各留最新 KEEP=2000 条(到顶才淘汰该板块最旧)
      · 生成今日综述 newsDigest
      · 写 news_data_latest.js
  → 抓到 <10 条则放弃(防覆盖)
  → 有新数据才 git push + vercel --prod 部署
```

无新条目的小时:不改文件、不部署。

## 文件说明

| 文件 | 作用 |
|---|---|
| `index.html` | 首页:今日综述卡 + 头条 + 24h热榜 + 分类信息流 |
| `detail.html` | 详情页:AI 中文正文 + 关联标的 |
| `stock.html` | 行情页:点标的看实时行情;无参时汇总当日全部标的 |
| `assets/theme.css` | 设计系统(含暗色模式) |
| `assets/app.js` | 前端共享逻辑(分类封面、加载数据、标的标签等) |
| `fetch_rss.py` | RSS 抓取(纯标准库) |
| `enrich_news.py` | 抓取→去重→Qwen 富化→写数据(管线主程序) |
| `api/quote.js` | Vercel serverless:代理新浪财经取实时行情 |
| `api/chat.js` | Vercel serverless:AI 对话(服务端召回站内资讯,可切 Qwen/Kimi) |
| `news_data_latest.js` | 前端读取的数据(`const newsData` + `const newsDigest`),由管线生成 |
| `seen_urls.json` | 去重用的已见 URL 清单(最多 5000),由管线维护 |
| `recover_history.py` | 一次性工具:从 git 历史恢复旧的已富化新闻 |
| `fetch_currents_news.py` | 旧 Currents 抓取,已弃用(保留备份) |

## 怎么改

- **加/删数据源**:`fetch_rss.py` 的 `FEEDS` 列表(每项 `(来源名, RSS地址, 默认分类)`)。每源取多少条改 `PER_FEED`。
- **每小时富化上限 / 每板块累计上限**:`enrich_news.py` 顶部 `CAP`(默认 50)、`KEEP`(默认 2000,**按板块**);也可用环境变量 `AID_CAP` / `AID_KEEP` 覆盖(如一次性补量:`AID_CAP=200 python3 enrich_news.py`)。
- **更新频率**:`.github/workflows/update-news.yml` 的 `cron`。
- **新闻富化模型**:`enrich_news.py` 的 `QWEN_MODEL` / `QWEN_URL`(阿里云 Anthropic 兼容端点)。
- **问 AI 模型**:`api/chat.js` 默认 Qwen;Vercel 设 `CHAT_PROVIDER=kimi` 后走 Kimi。
- **分类与封面配色**:`assets/app.js` 的 `CATS`;`enrich_news.py` 的 `CATEGORIES`(两处分类要一致)。

## 实时行情

`stock.html?symbol=NVDA` → 调 `/api/quote?symbol=NVDA,0700.HK,600519.SH`(支持批量)。
- 数据源:新浪财经 `hq.sinajs.cn`(免费、无 key),serverless 内 GBK 解码、分 US/HK/CN 解析。
- 代码格式:美股直接代码(NVDA);港股 `0700.HK`;A股 `600519.SH` / `000001.SZ`。
- **时效**:A股/港股盘中接近实时,美股约延迟 15 分钟。新浪为非官方接口,若失效需换源(腾讯 `qt.gtimg.cn` / Yahoo,或接已登录的 Longbridge CLI)。
- 红涨绿跌(中国习惯)。

## AI 对话(问AI)

底栏「问AI」打开对话面板 → 前端只 POST `{ question }` 给 `/api/chat` → 服务端从 `news_data_latest.js` 召回相关资讯,必要时做网页检索,再交给模型回答。
- 默认:`CHAT_PROVIDER=qwen`,使用 `QWEN_KEY`,模型 `QWEN_MODEL` 默认 `qwen3.7-max`。
- Kimi:`CHAT_PROVIDER=kimi`,默认走 Kimi Coding Plan,使用 `KIMI_KEY`,模型 `KIMI_MODEL` 默认 `kimi-for-coding`。
- 如使用普通 Moonshot OpenAI-compatible API,设 `KIMI_API_STYLE=openai`、`MOONSHOT_API_KEY`;API base 默认 `https://api.moonshot.ai/v1`,中国区可设 `KIMI_BASE_URL=https://api.moonshot.cn/v1`。
- ⚠️ 该端点公开无鉴权,已有限流,但仍会消耗模型 token。若被刷需加口令或登录态。

## 部署 / Secrets

- GitHub→Vercel 自动部署未接通,改由 Action 内 `vercel --prod` 部署。
- 仓库 Secrets(GitHub Actions 用):`QWEN_KEY`、`VERCEL_TOKEN`、`VERCEL_ORG_ID`、`VERCEL_PROJECT_ID`。
- Vercel 环境变量(serverless 函数用):`QWEN_KEY`;若切 Kimi Coding Plan,加 `CHAT_PROVIDER=kimi`、`KIMI_KEY`;若切普通 Moonshot API,加 `CHAT_PROVIDER=kimi`、`KIMI_API_STYLE=openai`、`MOONSHOT_API_KEY`。
- 本地手动部署:`npx vercel deploy --prod --token <VERCEL_TOKEN>`。

## 成本

抓取 / 调度(GitHub Action 公开仓库)/ 托管(Vercel)/ RSS / 新浪行情 —— 全免费。
唯一按量计费:Qwen(每小时只翻新条目,无新闻的小时近 0)。

## 已知限制

- 强制每条出利好标的 → 个别关联偏弱(reason 里会点明强弱)。
- 新浪行情非官方接口,稳定性不保证。
- `/api/chat` 公开无鉴权,有被刷烧 token 的风险(见上)。
- 部分小众分类(机器人/量子科技等)条目偏少,靠累计逐步填充。
