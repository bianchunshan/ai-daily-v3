# 前序 / QIANXU

## 品牌

名称：前序。品牌短句：科技的下一页。

“前”对应前沿与前瞻，“序”对应把连续变化的信息整理成可阅读的线索。名称不限定人工智能或日报频率，适合现有多领域科技资讯站。

图形以打开的一页为意象，湖绿色主体与右上珊瑚色折角构成向前打开的轮廓。字标采用简洁的中文无衬线字体，英文拼音作为辅助署名，不强制用户认识一个新英文词。

- 主色：湖绿 `#087F82`。
- 点色：珊瑚 `#F06450`。
- 文字：墨绿黑 `#1D2D2F`。
- 网页品牌强调色另使用更深的 `#076569`，小字号珊瑚文字使用 `#AA4938`，保证浅色背景可读性；证券涨跌红绿规则不变。

## 交付文件

- `assets/brand/qianxu-symbol-v1.png`：原生透明 Logo 图形，原始生成字节未改动。
- `design/qianxu-identity.html`：可直接在浏览器打开的品牌组合稿，含浅色、深色及小尺寸用法。
- `design/qianxu-identity.png`：上述组合稿的浏览器截图。
- 已更新首页、详情页、行情页、浏览器标题、favicon、主题色和 AI 助手品牌自称。
- 沿用 `https://ai-daily-v3.vercel.app`，不变更仓库、接口、抓取调度、模型或凭证。未重新打包 APK。

名称已做一般公开搜索，但这不是商标权利核验，不保证可注册；没有购买域名或提交商标申请。

## 生成与验证

- generation_route: built-in image_gen
- model: unknown (tool did not expose model identifier)
- original_path: /Users/steve/.codex/generated_images/019ef3dc-a9af-77f2-89f2-6a865ad29635/exec-115b1dae-bc38-48e4-9e08-b052a5545f52.png
- sha256: f90316e3de7af8532285485a866ff9e0d7c52e6f089d37c5993bc2404a79693f
- format: PNG
- dimensions: 1254x1254
- mode: RGBA
- bytes: 513805
- alpha_extrema: 0, 255
- fully_transparent_pixels: 1019028
- corner_alpha: 0, 0, 0, 0
- alpha_validation: pass
- edge_qa: pass; inspected on white and dark surfaces, no matte rectangle or obvious edge halo
- postprocessing: none; source copied byte-for-byte into project
- user_acceptance: not yet recorded

`tests/brand-check.cjs` 检查页面名、favicon、真实 Logo 图片加载、320/390px 布局、深浅色截图、详情及行情标识一致性。核心 JavaScript 测试 10 项通过。没有新增模型调用、后台任务或新闻批量处理。

## 原始提示词

```text
Use case: logo-brand.
Create ONE original, sophisticated standalone brand symbol for a Chinese frontier-technology news publication named 前序 (QIANXU), meaning the prelude / the next page of technology.
Asset: production-ready logo icon, no wordmark and absolutely no text.
Concept: an open editorial page turning forward. A compact, asymmetric geometric monogram built from two bold interlocking folded-page forms. The large deep lagoon-teal shape forms a crisp open near-square page / portal; a small coral-red folded corner projects diagonally toward the upper right. The transparent negative space between the page forms must create a strong memorable forward-opening aperture, not a stock arrow. Use only two or three large flat shapes, thick masses, expertly balanced negative space, coherent 45-degree folds, subtle corner precision. This is a publishing mark with technological confidence, not a literal book drawing.
Colors: dominant deep lagoon teal #087F82 and a restrained coral #F06450 fold accent (at most 15% of the symbol). Flat solid fills; no gradients, no outline strokes, no 3D, no shadows, no texture, no lighting, no globe, no atom, no sparkle, no circuit, no brain, no rounded app-tile background.
Composition: one centered near-square symbol filling about 82% of the square canvas, generous but not excessive transparent padding; perfectly clean silhouette, legible as a 24px favicon and a 36px masthead icon. Do not include variants, mockups, a presentation board, rulers, annotations or any letters.
Return a native transparent PNG whose area outside the subject contains genuine pixel transparency with a real alpha channel. Keep the complete symbol uncropped with transparent padding. Do not draw a background, floor, cast shadow, glow, border, watermark or transparency-preview pattern.
```

