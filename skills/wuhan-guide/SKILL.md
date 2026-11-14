---
name: wuhan-guide
display_name: 武汉导览
display_name_en: Wuhan Guide
description: 当用户表达「武汉全景导览」或「武汉线路／行程查询」两类意图时使用。全景导览输出单文件离线交互地图 HTML（无标签手绘底图 + 18 个橙金编号 DOM 标签 + G1–G9 多选高亮 + 鼠标 3D 倾斜 + 景点简介弹窗）与按片区编号清单，零接口调用、零网络请求；线路查询按 G1–G9 代号调用接口，输出结构化文字行程单，并在同一张页面的底部行程抽屉铺开对应线路的行程卡片。两种模式共用同一份模板与同一个 ASCII 文件名 wuhan-guide.html，同名幂等覆盖，各自只执行一次脚本调用。单个景点详情交给 wuhan-scenic-intro，城市地情交给 wuhan-intro。
description_zh: 「武汉全景导览」与「武汉线路／行程查询」的统一入口：一张单页双视图（离线交互地图 + 底部行程抽屉）；导览零接口只给路径与清单，线路一次调用同时产出文字行程单与同名单页。
description_en: Unified entry for "Wuhan panorama tour" and "Wuhan itinerary query" intents. Emits one offline single-page dual-view deliverable: an interactive 18-spot map plus a bottom itinerary drawer. The panorama mode makes zero API calls; the route mode makes exactly one call and writes the same wuhan-guide.html with itinerary cards.
examples_zh:
- "武汉全景导览"
- "给我一张武汉全景地图"
- "武汉整体看看有哪些景点，来张导览图"
- "武汉玩一天怎么玩"
- "推荐武汉 2 日游"
- "G1 和 G2 有哪些景点"
- "黄鹤楼在哪条线路上"
examples_en:
- "Wuhan panorama tour"
- "Show me an interactive map of Wuhan"
- "How should I spend a day in Wuhan?"
- "Plan a 2-day Wuhan itinerary"
- "Which spots are on G1 and G2?"
version: 2.0.0
author: 武汉海辞科技有限公司
allowed-tools: Bash(python3)
---

<!-- SPDX-License-Identifier: GPL-3.0-only | Copyright (C) 2026 武汉海辞科技有限公司 -->

# 武汉导览技能

## 目的

把「看全城」与「排行程」收敛到同一个技能、同一张页面。页面上半部是全屏沉浸的手绘全景地图：底图无标签，18 个景点由 DOM 渲染为「橙金编号 + 名称」玻璃标签，支持 G1–G9 多选高亮、鼠标 3D 倾斜与景点简介弹窗；页面底部是磨砂玻璃行程抽屉：全景导览时收起并显示引导占位，线路查询时**默认展开**、以**单列**铺开行程卡片；抽屉内不再重复放置线路与 G1–G9 按钮（地图控制条已有）。两种意图共用同一份模板与同一个输出文件名，后者同名覆盖前者。

| 意图 | 模式 | 网络 | 一次脚本调用产出 |
| --- | --- | --- | --- |
| 武汉全景导览 | `map` | 零接口、零请求 | stdout 页面路径 + 按片区编号清单；抽屉为引导占位 |
| 线路／行程查询 | `route` | 1 次接口（timeout 60s） | stdout 文字行程单 + 同名单页（抽屉默认展开，单列铺开行程卡片） |

## 何时使用

| 用户说法 | 模式 |
| --- | --- |
| 「武汉全景导览」「给我一张武汉全景地图」「武汉整体看看有哪些景点」「打开武汉导览地图」 | `map` |
| 「推荐武汉 2 日游」「武汉玩一天怎么玩」「G1 和 G2 有哪些景点」「内东湖主线怎么玩」「黄鹤楼在哪条线」「2 日游加光谷」「--all 等价的全线路」 | `route` |

**不要**把以下情况接到本技能：

| 情况 | 交给谁 |
| --- | --- |
| 单个景点详情、玩法、季节主题、景点对比、讲解词 | `wuhan-scenic-intro` |
| 城市历史、地理、人口经济等地方志内容 | `wuhan-intro` |
| 社区与大赛介绍 | `shuming-spu-intro` / `saig-intro` |
| 点到点导航、实时路况、具体交通走法 | 不在能力范围内，如实说明 |

判断要点：要的是**可操作的地图视图**走 `map`；要的是**线路安排／行程单**走 `route`。两者同时出现时按用户主要诉求择一，不自动串联第二个脚本。

## 工作流程

### 第一步：判定模式（不调用任何工具）

按上表把用户问题归到 `map` 或 `route`，并准备 `<工作区绝对路径>/wuhan-guide.html`。输出必须落在工作区内且文件名保持 ASCII：预览服务只服务工作区，写到 `/tmp` 等临时目录会返回 `Forbidden(403)`，脚本会在 stderr 给出警告。

### 模式 A · 全景导览（零接口）

1. 执行**一次**脚本，产出只含地图与引导占位的单页：

   ```bash
   python3 skills/wuhan-guide/scripts/show_map.py --out <工作区绝对路径>/wuhan-guide.html
   ```

2. 把脚本 **stdout 原样回显**：页面路径 + 一行说明 + 按片区编号景点清单。清单由脚本从模板的 18 个 `data-no`／`data-title` 实时读取，与内置 `AREA_GROUPS` 交叉校验；不凭记忆另写一份、不改动编号、不增删景点、不补写景点介绍。用户说「3 号是什么」「看看 12 号」时直接按本轮 stdout 回答名称与所属片区，不新增查询。

3. 本模式是 L0 档位的**视图交付特例**：不调用任何知识库接口、不生成解说词、不生成行程单、不做来源标注、不追加「可继续深入」方向、不自动串联其他技能；给完路径与清单即结束本轮。

4. 页面底部行程抽屉在此模式只显示**引导占位**（说明如何说出天数／线路代号），不是行程数据，不得把占位描述成行程单。控制条 G1–G9 在此模式仍是纯本地多选高亮筛选，不调接口。

### 模式 B · 线路查询（一次接口调用）

1. 按 `references/route_codes.md` 的代号字典、衔接链与 N 日游推导表，把自然语言解析为代号数组（`--days N`、`--find <景点名>`、`--all` 或直接代号；保留 `--no-sort` 与 `--no-image` 排查能力）。

2. 执行**一次**脚本，同时取得 stdout 文字行程单与同一张单页：

   ```bash
   python3 skills/wuhan-guide/scripts/query_route.py --days 2 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py G1 G2 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py --find 黄鹤楼 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py --all --out <工作区绝对路径>/wuhan-guide.html
   ```

   `--cards` 为兼容旧调用保留的空开关：合并后单页始终生成，可省略。省略 `--out` 时脚本写到当前工作目录下的 `wuhan-guide.html`，实际调用仍应显式传工作区绝对路径。

3. **先文字快答、页面随后输出**：文字快答基于 `references/route_codes.md` 的零调用字典，或基于同一次脚本的 stdout；随后回显页面路径与完整行程。一次调用同时完成两件事，**禁止为「先文字、后页面」执行两次脚本**（会重复拉全量记录与下载图片），也不要在同轮额外生成另一份 HTML。

   宿主支持「先输出中间文本、再继续工具调用」时先给文字快答，再执行脚本、补充页面结果；若中间文本会被判定为本轮结束，则把「文字快答在前、页面路径与完整行程在后」放进同一条最终回复，不得漏掉页面。

4. 忠实使用 stdout 的景点名称、类型、停留时长、推荐指数、点评与片区，不增删、不改写、不自行重排；每条线路内部顺序以脚本输出（接口「排序」递增）为准。线路先后以脚本给出的天数顺序为准，保留「片区／本线时长／景点数／全程总时长」。单条线路只呈现该线路内容。

5. 页面底部抽屉在此模式**默认展开**，单列铺开各线路的行程卡片，卡片带 `data-route` 标记；抽屉内不再重复放置线路与 G1–G9 按钮，地图控制条的 G1–G9 仍可多选，联动高亮地图点位并过滤卡片。未选线路时展示全部卡片。

6. 脚本以非零退出码失败时（HTTP 401/404/405/500、网络异常、模板校验失败），**向用户说明失败并给出 stderr 原始错误**，不得改用自身记忆回答线路内容、不重试、不换脚本再调。接口失败时脚本不写也不覆盖既有页面。

### 两种模式的共同约束

- 同一问题只落一个模式、最多一条 `Bash(python3)` 命令；不自动串联其他技能。
- 产物固定为 `wuhan-guide.html`，两种模式同名幂等覆盖；先导览后线路时，后者覆盖前者为含行程卡片的版本，属预期行为，需向用户说明页面已更新。
- `map` 模式不做来源标注（无知识库来源）；`route` 模式按 `agents/jing-xiao-wu.md` 的输出规范标注来源并说明实时信息边界。

## 回答约束

- 一切景点名称、编号、片区分组以脚本 stdout 为准；不补票价、开放时间、交通、点评等未经核实的信息。
- 不把引导占位说成行程数据，不把地图上的本地线路高亮说成「已查询接口」。
- 不在同一轮里额外生成另一份 HTML、讲解词或缩略卡页面。
- 页面上的热区坐标维护在 `assets/wuhan-guide-map.html` 的 `style="--x:..;--y:..;--w:..;--h:.."` 中，`--x/--y` 是中心百分比；底图不含文字或圆牌，18 个标签由 `.spot-chip`（`.spot-no` + `.spot-name`）DOM 渲染，编号与名称取自按钮的 `data-no`／`data-title`，脚本交叉校验。标签用自身 `translate(-50%,-50%)` 居中，不与 GSAP 控制的父元素 `transform` 冲突。窄屏（≤650px）降级为只显示橙金编号牌。
- 9 个 `.route-btn` 的 `data-spots` 是「线路 → 点位编号」唯一映射源；多选时对并集点位加 `.is-matched`、其余加 `.is-dimmed`，只切 class，不触碰 `transform`。

## 维护约定

- 模板 `assets/wuhan-guide-map.html` 是唯一视觉与交互事实源，含内联 GSAP 3.12.5（保留许可头）与 2MB 级单行 base64 底图，纯 LF 行尾。编辑必须用精确字符串替换，禁止整文件重排、统一行尾或格式化，否则会破坏 base64 行。
- 模板中三个占位符各恰好出现一次：`__GUIDE_CARDS_CSS__`（head 内作用域化卡片样式）、`__GUIDE_CARDS_HTML__`（抽屉内容挂载点）、`__GUIDE_MODE__`（独立抽屉脚本的模式常量 `map`／`route`）。`guide_common.load_template()` 会校验数量，缺失或重复直接报错。
- 抽屉逻辑放在业务 IIFE **之后**的独立 `<script>`：业务脚本开头有 `if (!window.gsap) return;`，塞进 IIFE 会在 GSAP 失效时被连带跳过。
- 抽屉是 `.app` 内的普通文档流面板（`position:relative`），**不要改回 `fixed`/`sticky` 浮层**：实测 fixed 展开后会盖住 7 个地图热区；展开时用 `scrollIntoView` 把抽屉滚入视口。线路模式初始化即 `setOpen(true)` 默认展开并滚入视口，导览模式保持收起。点位点击只更新把手提示并做一次脉冲，不改变抽屉状态，避免与景点详情弹窗争抢视口。
- 行程卡 CSS 必须全部作用域到 `.gd-cards` 并使用 `gc-` 前缀，禁止 `body`／`*` 等全局规则，否则会破坏地图布局与窄屏降级。
- 新增 DOM 不得复用 `class="hotspot"` 或 `class="route-btn"`：`guide_common.py` 的 `BUTTON_RE`／`ROUTE_BTN_RE` 强校验 18 与 9 的数量。抽屉内不再放置 `gd-route-btn` 等线路按钮，避免与地图控制条重复。
- 新增景点一律追加编号末尾，保持既有 1—18 稳定；改热区（增删、改名、调编号）必须同步 `guide_common.py` 的 `AREA_GROUPS` 顺序，自带编号一致性校验会直接报错。
- stdout 为用户可见正文（页面路径、按片区清单、文字行程单），stderr 为运行元数据（来源、热区／线路数、sha256 前 16、预览 403 提示、接口与图片统计）。禁止打印 base64、接口原始大 payload 或任何 PII。

## 资源

- `assets/wuhan-guide-map.html`：唯一单页模板（约 2.2MB 单文件）。18 个 DOM 景点标签、G1–G9 多选筛选、3D 倾斜／弹窗、底部行程抽屉与三个占位符均在此文件内；无 CDN、无外链，离线可预览。
- `scripts/guide_common.py`：唯一渲染契约与共享工具。占位符常量、`load_template()`、`validate_template()`、`render_page()`（精确替换 + 临时文件 + `os.replace` 原子写）、`parse_spots`／`parse_routes`／`AREA_GROUPS`／`render_list`／`preview_hint`／`page_digest`，两个入口共用。
- `scripts/show_map.py`：导览模式薄入口，零网络、零接口，注入引导占位与 `map` 模式。
- `scripts/query_route.py`：线路模式入口。保留 `fetch_records()`／`normalize()`／`build_thumbs()`／`render()` 与全套 CLI（`codes`／`--days`／`--find`／`--all`／`--no-sort`／`--no-image`／`--out`）；`render_card_fragment()` 只返回作用域化 CSS 与卡片片段，交给 `guide_common.render_page()` 注入同一模板。图片默认并发预取后 base64 内联，单张内联失败则省略该图并给出占位说明，页面不产生任何外链请求；`--no-image` 可切换轻量模式。
- `references/route_codes.md`：代号字典、衔接链、N 日游推导表、景点→代号速查；仅作零调用文字快答字典，不含接口 13 字段明细，不能替代接口数据。
- `references/api_reference.md`：接口地址、请求体、响应结构、错误码与环境变量，排查调用问题时查阅。
