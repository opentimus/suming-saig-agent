---
name: wuhan-guide
display_name: 武汉导览
display_name_en: Wuhan Guide
description: 当用户表达「武汉全景导览」或「武汉线路／行程查询」两类意图时使用。全景导览输出离线交互地图 HTML（可拖动手绘底图 + 由 spots.json 驱动的橙金编号 DOM 标签 + G1–G9 多选高亮 + 景点简介弹窗 + 可视化景点编辑模式）与按片区编号清单，零接口调用、零网络请求；线路查询按 G1–G9 代号调用接口，输出结构化文字行程单，并在同一张页面底部的固定行程面板里按 G 分组铺开对应线路的行程卡片。两种模式共用同一份模板与同一个 ASCII 文件名 wuhan-guide.html，同名幂等覆盖，各自只执行一次脚本调用。单个景点详情、城市地情、社区与大赛介绍等检索类问题交给 saig-spu-rag。
description_zh: 「武汉全景导览」与「武汉线路／行程查询」的统一入口：一张单页双视图（离线交互地图 + 底部固定行程面板）；导览零接口只给路径与清单，线路一次调用同时产出文字行程单与同名单页；地图支持本地可视化编辑景点。
description_en: Unified entry for "Wuhan panorama tour" and "Wuhan itinerary query" intents. Emits one offline single-page dual-view deliverable: a data-driven interactive spot map with a local visual editor plus a bottom itinerary drawer. The panorama mode makes zero API calls; the route mode makes exactly one call and writes the same wuhan-guide.html with itinerary cards.
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
version: 2.2.0
author: 武汉海辞科技有限公司
allowed-tools: Bash(python3)
---

<!-- SPDX-License-Identifier: GPL-3.0-only | Copyright (C) 2026 武汉海辞科技有限公司 -->

# 武汉导览技能

## 目的

把「看全城」与「排行程」收敛到同一个技能、同一张页面。页面上半部是可拖动的手绘全景地图：竖版武汉三镇鸟瞰底图，固定高度视口内拖动查看全图，方向键平移、右上角「复位视图」或 Home 键复位；景点唯一事实源是 `assets/spots.json`，生成器按数组顺序渲染「橙金编号 + 名称」玻璃标签、线路按钮与页内数据块，景点随底图同层平移，支持 G1–G9 多选高亮与景点简介弹窗，并平滑居中到所选线路点位的包围盒。右上角「编辑景点」开启本地编辑模式：拖动定位、点击空白新增、改名称／类型／简介／所属线路或删除，改动写入 localStorage，可导出／导入 JSON，不写回仓库与接口。底部磨砂玻璃行程面板**固定展开、不可折叠**：导览时显示引导占位，线路查询时按 G1–G9 每组一张卡片（标题如「G1 · 龟蛇主线」），组内单列铺开；只显示选中组，未选时为空并显示占位提示。两种意图共用同一份模板与同一个输出文件名，后者同名覆盖前者。

## 何时使用

| 用户说法 | 模式 |
| --- | --- |
| 「武汉全景导览」「给我一张武汉全景地图」「武汉整体看看有哪些景点」「打开武汉导览地图」 | `map` |
| 「推荐武汉 2 日游」「武汉玩一天怎么玩」「G1 和 G2 有哪些景点」「内东湖主线怎么玩」「黄鹤楼在哪条线」「2 日游加光谷」「--all 等价的全线路」 | `route` |
| 「不去黄鹤楼」「把东湖换成汉街」「半天怎么玩」「3 小时」「从汉口出发」「想要夜景/美食/亲子」 | `route`（用 `--exclude/--replace/--hours/--area/--theme` 微调） |

**不要**把以下情况接到本技能：

| 情况 | 交给谁 |
| --- | --- |
| 单个景点详情、玩法、季节主题、景点对比、讲解词 | `saig-spu-rag` |
| 城市历史、地理、人口经济等《武汉概览》背景内容 | `saig-spu-rag` |
| 数命SPU 社区、SAIG 大赛介绍 | `saig-spu-rag` |
| 点到点导航、实时路况、具体交通走法 | 不在能力范围内，如实说明 |

判断要点：要的是**可操作的地图视图**走 `map`；要的是**线路安排／行程单**走 `route`。两者同时出现时按用户主要诉求择一，不自动串联第二个脚本。

## 其他规划需求：最小适配原则

行程需求超出常见模式时，**优先用现有参数映射**；确需扩展时以现有脚本为基础做最小增量：

| 需求示例 | 做法（向后兼容，不改抓取/渲染/模板） |
| --- | --- |
| 不去某景点 / 不要某条线 | `--exclude 黄鹤楼` 或 `--exclude G3` |
| 把某景点换成另一个 | `--replace 东湖=汉街`（旧景点写完整景点名，新景点须在线路数据中；只在本次所选线路内生效，同名景点在多条线路出现时全部替换，找不到或匹配歧义时脚本直接报错退出、不生成页面） |
| 半天 / 3 小时 | `--half` 或 `--hours 3`（按线路累计时长裁剪，至少保留一条） |
| 从汉口出发 / 想在某片区 | `--area 汉口` |
| 想要夜景 / 美食 / 亲子 | `--theme 夜景`（匹配类型、景点、点评） |
| 让页面只默认选中某几组 | `--preselect G1,G2`（与本次行程取交集，非法代号忽略） |

- 现有参数能表达时，不要新增代码；确需新增能力时，只加可选参数与客户端过滤/裁剪，复用 `fetch_records()`、`normalize()`、`render()`、`render_card_fragment()` 与模板链路，**禁止重写抓取、归一化、渲染或模板**。
- 新参数默认关闭，缺省行为与现有完全一致。

## 工作流程

### 第一步：判定模式（不调用任何工具）

按上表把用户问题归到 `map` 或 `route`，并准备 `<工作区绝对路径>/wuhan-guide.html`。输出必须落在工作区内且文件名保持 ASCII：预览服务只服务工作区，写到 `/tmp` 等临时目录会返回 `Forbidden(403)`，脚本会在 stderr 给出警告。

### 模式 A · 全景导览（零接口）

1. 执行**一次**脚本，产出只含地图与引导占位的单页：

   ```bash
   python3 skills/wuhan-guide/scripts/show_map.py --out <工作区绝对路径>/wuhan-guide.html
   ```

2. 把脚本结果用**自然语言呈现**：页面路径 + 按片区编号景点清单。清单由脚本从 `assets/spots.json` 读取（编号＝数组顺序，片区按首次出现分组）；不凭记忆另写一份、不改动编号、不增删景点、不补写景点介绍。用户说「3 号是什么」「看看 12 号」时直接按本轮脚本结果回答名称与所属片区，不新增查询。

3. 本模式是 L0 档位的**视图交付特例**：不调用任何知识库接口、不生成解说词、不生成行程单、不做来源标注、不追加「可继续深入」方向、不自动串联其他技能；给完路径与清单即结束本轮。

4. 页面底部行程面板在此模式固定展开，只显示**引导占位**（说明如何说出天数／线路代号），不是行程数据，不得把占位描述成行程单。控制条 G1–G9 在此模式仍是纯本地多选高亮筛选，不调接口。

### 模式 B · 线路查询（一次接口调用）

1. 按 `references/route_codes.md` 的代号字典、衔接链与 N 日游推导表，把自然语言解析为代号数组（`--days N`、`--find <景点名>`、`--all` 或直接代号），再按需叠加 `--exclude/--replace/--half/--hours/--area/--theme/--preselect` 微调（保留 `--no-sort` 与 `--no-image` 排查能力）。

2. 执行**一次**脚本，同时取得 stdout 文字行程单与同一张单页：

   ```bash
   python3 skills/wuhan-guide/scripts/query_route.py --days 2 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py G1 G2 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py --find 黄鹤楼 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py --all --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py --days 2 --exclude 黄鹤楼 --hours 8 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py G1 G2 --replace 东湖=汉街 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py --all --area 汉口 --theme 夜景 --out <工作区绝对路径>/wuhan-guide.html
  python3 skills/wuhan-guide/scripts/query_route.py --days 2 --exclude 龟山公园 --preselect G1,G2 --out <工作区绝对路径>/wuhan-guide.html
   ```

   `--cards` 为兼容旧调用保留的空开关：合并后单页始终生成，可省略。省略 `--out` 时脚本写到当前工作目录下的 `wuhan-guide.html`，实际调用仍应显式传工作区绝对路径。

3. **先文字快答、页面随后输出**：文字快答基于 `references/route_codes.md` 的零调用字典，或基于同一次脚本的 stdout；随后回显页面路径与完整行程。一次调用同时完成两件事，**禁止为「先文字、后页面」执行两次脚本**（会重复拉全量记录与下载图片），也不要在同轮额外生成另一份 HTML。

   宿主支持「先输出中间文本、再继续工具调用」时先给文字快答，再执行脚本、补充页面结果；若中间文本会被判定为本轮结束，则把「文字快答在前、页面路径与完整行程在后」放进同一条最终回复，不得漏掉页面。

4. 忠实使用 stdout 的景点名称、类型、停留时长、推荐指数、点评与片区，不增删、不改写、不自行重排；每条线路内部顺序以脚本输出（接口「排序」递增）为准。线路先后以脚本给出的天数顺序为准，保留「片区／本线时长／景点数／全程总时长」。单条线路只呈现该线路内容。

5. 页面底部行程面板在此模式**固定展开、不提供折叠入口**，按 G1–G9 每组一张卡片（标题为「Gx · 线路名」），组内以紧凑单列列出该组景点，整组带 `data-route` 标记；行程区内不再重复放置线路与 G1–G9 按钮，地图控制条的 G1–G9 仍可多选，联动高亮地图点位并过滤卡片，同时把视图平滑居中到所选线路点位的包围盒中心。**未选线路时卡片区为空**（显示「未选择线路」占位），这是刻意行为。每组卡片右上角有「+」，可把未在本组的景点加进来（从原组移动，不复制），每行最右侧「×」把景点移出本组；增删会即时重编号并更新「N 个景点」，改动只作用于当前页面，不写回接口，刷新即恢复原始行程。标题行右侧是「分享」按钮：把下方**当前可见**的组（含本次增删）整理成纯文本，无可见组时按钮禁用，优先调用系统分享面板，不支持时复制到剪贴板并提示「已复制」；导览模式没有行程数据，分享按钮隐藏。

6. 脚本以非零退出码失败时（HTTP 401/404/405/500、网络异常、模板校验失败），**向用户说明失败并给出 stderr 原始错误**，不得改用自身记忆回答线路内容、不重试、不换脚本再调。接口失败时脚本不写也不覆盖既有页面。

### 两种模式的共同约束

- 同一问题只落一个模式、最多一条 `Bash(python3)` 命令；不自动串联其他技能。
- 产物固定为 `wuhan-guide.html`，两种模式同名幂等覆盖；先导览后线路时，后者覆盖前者为含行程卡片的版本，属预期行为，需向用户说明页面已更新。
- **交付物只有 `wuhan-guide.html`**：同目录 `wuhan-guide-map.jpg` 是页面相对引用的内部资源，脚本会自动写出，但**不要**把它当作独立交付文件列出、也不要在回复里生成 jpg 文件卡片；底图随页面加载即可。确需单文件转发时加 `--inline-image`，底图会 base64 内联，代价是首屏解码变慢。
- **脚本无会话，修订须整串传参**：每次调用都重新拉接口、重渲染、原子覆盖同名文件；修订时把当前完整行程配置（如 `--days 2 --exclude 龟山公园 --preselect G1,G2`）叠加增量后整串重传，禁止只传增量，也不要假设上次参数被记住。
- **页面内编辑不持久**：组内增删/拖动仅当页生效（localStorage + baseHash），重新生成即失效；需跨修订保留时把改动回写为生成参数（`--exclude`/`--replace` 等），并在交付时说明「页面内编辑不持久」。
- **以产物 HTML 为准**：同名覆盖可能遇预览缓存，判断配置是否生效应读取产物 HTML 实际内容（`aria-pressed`、`gc-hidden`、是否仍含已排除景点），不要只看预览面板；必要时用带查询串/新 hash 的预览 URL 打开。
- `map` 模式无知识库来源；`route` 模式按 `agents/jiang-xiao-shu.md` 的输出规范自然呈现、不暴露内部引用，并说明实时信息边界。

## 回答约束

- 一切景点名称、编号、片区分组以脚本 stdout 为准；不补票价、开放时间、交通、点评等未经核实的信息。
- 不把引导占位说成行程数据，不把地图上的本地线路高亮说成「已查询接口」。
- 不在同一轮里额外生成另一份 HTML、讲解词或缩略卡页面。
## 维护约定

只在改数据/模板/脚本/页面交互时才读 `references/maintenance.md`：模板注入契约、
编辑与拖动实现约束、事件委托与性能限制、CLI 与文件所有权都在那里；日常问答与生成页面不需要。

## 资源

- `assets/spots.json`：景点唯一数据源（名称/类型/简介/坐标/片区/所属线路），数组顺序即编号。
- `assets/wuhan-guide-map.html`：唯一单页模板，内联热区、线路按钮、数据块与导览占位，无 CDN、无外链，双击或预览即可完整使用。
- `assets/wuhan-guide-map.jpg`：外置底图（1400×1592 JPEG，约 850KB）；改图须同步模板 `<img class="map-art">` 的 `width`/`height`。
- `scripts/guide_common.py`：共享渲染契约（数据校验、块注入、原子写），两个入口共用。
- `scripts/show_map.py`：导览模式入口，零网络、零接口。
- `scripts/query_route.py`：线路模式入口，一次接口调用 + 缩略图并发预览（带磁盘缓存），产出文字行程单与同名单页。
- `references/route_codes.md`：G1–G9 代号字典与景点速查，零调用文字快答用。
- `references/api_reference.md`：接口地址、请求体、错误码，排查调用问题时查阅。
- `references/maintenance.md`：改数据/模板/脚本/页面交互前必读的维护约定。
