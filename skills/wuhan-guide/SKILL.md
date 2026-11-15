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

把「看全城」与「排行程」收敛到同一个技能、同一张页面。页面上半部是可拖动的手绘全景地图：底图为竖版武汉三镇鸟瞰图（自带行政区注记），固定高度视口内用鼠标／触摸拖动查看全图，方向键可平移、右上角「复位视图」或 Home 键回到初始位置；景点唯一事实源是 `assets/spots.json`，生成器按数组顺序渲染出「橙金编号 + 名称」玻璃标签、线路按钮与页内数据块，景点随底图同层平移，支持 G1–G9 多选高亮与景点简介弹窗（3D 倾斜已移除，换取拖动时的合成开销）；选中线路时视图平滑居中到该组点位的包围盒中心，取消选择则保持当前视野不动；右上角「编辑景点」可开启本地编辑模式：拖动定位、点击空白新增、点选改名称／类型／简介／所属线路或删除，改动写入浏览器 localStorage，可导出／导入 JSON，不写回仓库与接口。页面底部是磨砂玻璃行程面板：**固定展开、不可折叠**，全景导览时显示引导占位，线路查询时按 G1–G9 **每组一张卡片**（标题形如「G1 · 龟蛇主线」）、组内以紧凑单列列出该组景点；上方 G1–G9 与下方卡片严格对应，只显示选中组（未选时列表为空并显示占位提示）；面板内不再重复放置线路与 G1–G9 按钮（地图控制条已有）。两种意图共用同一份模板与同一个输出文件名，后者同名覆盖前者。

| 意图 | 模式 | 网络 | 一次脚本调用产出 |
| --- | --- | --- | --- |
| 武汉全景导览 | `map` | 零接口、零请求 | stdout 页面路径 + 按片区编号清单；行程面板为引导占位 |
| 线路／行程查询 | `route` | 1 次接口（timeout 60s） | stdout 文字行程单 + 同名单页（行程面板固定展开，按 G 分组、组内单列铺开行程卡片） |

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
| 把某景点换成另一个 | `--replace 东湖=汉街`（新景点须在线路数据中） |
| 半天 / 3 小时 | `--half` 或 `--hours 3`（按线路累计时长裁剪，至少保留一条） |
| 从汉口出发 / 想在某片区 | `--area 汉口` |
| 想要夜景 / 美食 / 亲子 | `--theme 夜景`（匹配类型、景点、点评） |

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

1. 按 `references/route_codes.md` 的代号字典、衔接链与 N 日游推导表，把自然语言解析为代号数组（`--days N`、`--find <景点名>`、`--all` 或直接代号），再按需叠加 `--exclude/--replace/--half/--hours/--area/--theme` 微调（保留 `--no-sort` 与 `--no-image` 排查能力）。

2. 执行**一次**脚本，同时取得 stdout 文字行程单与同一张单页：

   ```bash
   python3 skills/wuhan-guide/scripts/query_route.py --days 2 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py G1 G2 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py --find 黄鹤楼 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py --all --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py --days 2 --exclude 黄鹤楼 --hours 8 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py G1 G2 --replace 东湖=汉街 --out <工作区绝对路径>/wuhan-guide.html
   python3 skills/wuhan-guide/scripts/query_route.py --all --area 汉口 --theme 夜景 --out <工作区绝对路径>/wuhan-guide.html
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
- 交付形态默认是**两个文件**：`wuhan-guide.html` + 同目录的 `wuhan-guide-map.jpg`（脚本自动写出）。向用户说明时点明两者需一起拷走/转发；确需单文件时加 `--inline-image`，底图会重新 base64 内联，代价是首屏解码变慢。
- `map` 模式无知识库来源；`route` 模式按 `agents/jing-xiao-wu.md` 的输出规范自然呈现、不暴露内部引用，并说明实时信息边界。

## 回答约束

- 一切景点名称、编号、片区分组以脚本 stdout 为准；不补票价、开放时间、交通、点评等未经核实的信息。
- 不把引导占位说成行程数据，不把地图上的本地线路高亮说成「已查询接口」。
- 不在同一轮里额外生成另一份 HTML、讲解词或缩略卡页面。
- 景点坐标唯一维护在 `assets/spots.json` 的 `x/y/w`（中心百分比与宽度百分比）；生成器输出到热区 `style` 的 `--x/--y/--w`，`--h` 固定 88px。编号由数组顺序派生，浏览器内增删后自动重排；页面上改坐标只进 localStorage，不写回 JSON。标签由 `.spot-chip`（`.spot-no` + `.spot-name`）渲染，与底图同处 `.map-canvas`，用自身 `translate(-50%,-50%)` 居中，窄屏（≤650px）只显示编号牌。
- 9 个 `.route-btn` 的 `data-spots` 由每个景点的 `routes` 反推，是「线路 → 点位编号」唯一映射源；某条线路可以没有点位（`data-spots=""`）。多选时对并集点位加 `.is-matched`、其余加 `.is-dimmed`，只切 class，不触碰 `transform`。
- 地图编号牌的底色跟所属线路主题色一致：热区 `style` 注入 `--rc:var(--gN)`，`N` 取 `routes` 的第一条线路（如东湖 G2/G3 取 G2、龟山 G1/G6 取 G1），无线路的新增点位回退橙金 `#e69a32`；只染 `.spot-no` 编号块，名称胶囊保持白底玻璃质感。编辑模式切换线路时会同步改写 `--rc`。

## 维护约定

- 模板 `assets/wuhan-guide-map.html` 是唯一视觉与交互事实源，约 180KB，含内联 GSAP 3.12.5（保留许可头），纯 LF 行尾；底图已外置为同目录的 `assets/wuhan-guide-map.jpg`（1400×1592，JPEG q80，约 850KB）。
  **只许用脚本改，不许手改**：`tools/sync_template_defaults.py --write` 刷新四个默认块，`show_map.py` / `query_route.py` 负责注入与写出；`guide_common.load_template()` 会在读到 CRLF 时直接报错，`.gitattributes` 已把该文件标记为 `-text` 阻止 git 做换行转换。禁止在编辑器里格式化、全选重排或统一行尾。
- 景点数据唯一事实源是 `assets/spots.json`：`{version:1, spots:[{name,type,desc,x,y,w,area,routes}]}`，数组顺序即编号；`routes` 只写该景点所属的 G 代号。增删景点、改坐标／线路只改这个文件，再依次跑 `tools/sync_template_defaults.py --write`（刷模板默认块）与 `show_map.py --out ...`（生成页面）；热区、线路按钮与页内数据块都由 `guide_common` 生成。
- `type` / `area` / `desc` 必须是正式文案，不要留 `自定义点位`、`自定义 · 手动新增`、`编辑模式下新增的点位…` 这类编辑器占位值——它们会直接出现在按片区清单、详情弹窗与行程卡片里。`area` 只用既有片区名：`汉口 · 江岸／江汉`、`汉阳 · 龟山／月湖`、`武昌 · 黄鹤楼／长江大桥`、`武昌 · 中南／洪山`、`东湖 · 沙湖`、`光谷 · 南湖`，新增片区需同步确认清单可读性。
- 模板注入分两类，每个标记各恰好出现一次，`load_template()` 会校验数量，缺失或重复直接报错：
  - 单点令牌：`__GUIDE_CARDS_CSS__`（head 内作用域化卡片样式）、`__GUIDE_MODE__`（抽屉模式常量，模板直开时按「非 route 即 map」回退）。
  - 带默认内容的块：`__GUIDE_CARDS_HTML__`…`__GUIDE_CARDS_HTML_END__`（抽屉内容）、`__GUIDE_SPOTS_HTML__`…（热区）、`__GUIDE_ROUTE_BTNS__`…（线路按钮）、`__GUIDE_SPOTS_JSON__`…（内联数据）。块内预置 `spots.json` 当前快照对应的热区与按钮、合法 JSON 与导览占位，**模板可直接打开预览**；生成时整块替换（含起止注释），产物不保留任何标记。默认块是 `spots.json` 的快照，改数据后需要直开默认值同步时，用 `render_spots_html()`／`render_route_btns()`／`render_spots_json()` 的输出重刷对应块。
- 抽屉逻辑放在业务 IIFE **之后**的独立 `<script>`：业务脚本开头有 `if (!window.gsap) return;`，塞进 IIFE 会在 GSAP 失效时被连带跳过。
- 行程区是 `.app` 内的普通文档流区块（`position:relative`），**不要改回 `fixed`/`sticky` 浮层**：实测 fixed 展开后会盖住 7 个地图热区；页面加载后保持地图在首屏，不自动滚到卡片区。面板**固定展开、不可折叠**：标题栏是无交互的 `<div class="gd-handle">`，不要再加回折叠按钮、`gd-chevron`、`inert` 或 Escape 收起逻辑；也不要给 `.gc-route`（每个 G 组一张的卡片）加折叠控件。点位点击只更新标题提示并做一次脉冲，不改变面板状态，避免与景点详情弹窗争抢视口。
- 行程卡 CSS 必须全部作用域到 `.gd-cards` 并使用 `gc-` 前缀，禁止 `body`／`*` 等全局规则，否则会破坏地图布局与窄屏降级。
- G1–G9 的线路主题色集中定义在模板 `:root` 的 `--g1`…`--g9`：`.route-btn[data-route]` 用 `--rc` 取色，地图编号牌注入 `--rc`、行程卡组由 `render_card_fragment()` 写入内联 `--gc-accent:var(--gN)`，组标题色条、代号胶囊与组内 `.gc-num` 编号牌都取该变量（跨组移动后自动跟随新组色）。新增或改名线路时代号与色号必须一一对应，不要在业务 CSS 里另写一份硬编码颜色。
- 景点编辑脚本是业务 IIFE 之后的独立 `<script>`（同样为了 GSAP 失效时不连带失效）：状态来自 `#guideSpotsData`，只读写 DOM 与 localStorage（键 `wuhan-guide:spots:v1`），不写回 `spots.json`。存档带 `baseHash`（`guide_common.spots_digest()`），页面数据变化后旧存档自动作废并回退内置数据；导入做结构／名称唯一／坐标 0–100／线路代号校验，失败只提示不破坏当前视图。
- 属性面板的「编号」输入按顺延重排处理：把该景点 splice 到目标位置，其余景点编号随之重排，始终连续 1..N；导出 JSON 的数组顺序即新编号，**不要**在 JSON 里新增编号字段，线路映射继续由数组顺序派生。
- 热区 hover、详情弹窗、线路筛选与抽屉提示全部改为事件委托（`#hotspotLayer`、`.route-btns` 容器），因为编辑模式会整层重建热区与按钮；编辑脚本重建后派发 `guide:spots-changed`，业务层据此重新上色。禁止改回逐个 `.hotspot` 绑定。
- 抽屉内不再放置 `gd-route-btn` 等线路按钮，避免与地图控制条重复；新增 DOM 不要复用 `class="hotspot"` 或 `class="route-btn"` 作为纯装饰。
- 组内增删景点是纯前端编辑：`spotPool` 以景点名为键持有页面里已有的全部 `article.gc-card` 节点（数量随接口当次返回而定，不写死），「+」把候选节点移入目标组，「×」把节点从组内摘除，随后重编号并刷新「N 个景点」。每行左侧的 `.gc-drag` 把手用 pointer 事件在同一 `.gc-grid` 内上下移动节点（支持触屏，聚焦后 ↑↓ 也可调整），松手后重编号。**不要**为这些编辑引入接口写回、localStorage 或额外数据文件；刷新页面即回到接口原始行程，这是刻意行为。
- 分享按钮 `#guideShare` 取代了旧的「N 组已选」徽标：`itineraryText()` 从 DOM 读取当前 9 组卡片（含增删）拼文本，`navigator.share` 优先、`clipboard.writeText` 兜底、最后 `execCommand` 复制；成功后按钮短暂显示「已分享／已复制」。改这块时保持“从 DOM 取数”，不要另建一份行程数据源，否则会和筛选、增删状态脱节。
- 地图拖动由独立的 vanilla JS `<script>` 实现，不依赖 GSAP：`.map-shell` 是固定高度视口（`overflow:clip` + `touch-action:none`），`.map-canvas` 包住 `<img class="map-art">` 与 `.hotspot-layer`，只改 `.map-canvas` 的 `transform:translate3d()` 并钳制到 `[minX,0] / [minY,0]`。**尺寸只在 measure() 里读一次**（首帧、图片 load、resize），pointermove 里只做算术与样式写，且写入用 `scheduleApply()` 合并到下一帧——否则每帧读 `clientWidth/offsetWidth` 会强制同步布局。视口用 `clip` 而非 `hidden`：`hidden` 仍是可滚动容器，聚焦边缘景点会被浏览器内部滚动、打乱视图。**不要**给 shell 用 `setPointerCapture`（会把点位 `click` 的 target 重定向到 shell，弹窗失效），改用 window 级 `pointermove/pointerup`；拖动超过 6px 时在捕获阶段吞掉随后那次 `click`，避免误开详情弹窗。右上角「复位视图」与 Home／0 键回到初始视图。
- 生成页面时编号由 `spots.json` 数组顺序决定；浏览器内新增景点追加到末尾，删除后自动重排。不要把编号写进 JSON，也不要再引入第二份景点清单或 `AREA_GROUPS` 之类的硬编码分组。
- 视图居中走自定义事件 `guide:pan-to`（`detail={x,y,duration}`，x/y 为相对底图的百分比），由平移 IIFE 换算成 `translate3d` 并做 400ms easing；`px/py` 是该 IIFE 的私有状态，**不要**再从其它脚本直接改 `.map-canvas` 的 `transform`，否则两处写同一属性必然打架。动画期间同样挂 `is-panning`（摘掉标签模糊），用户 pointerdown 会 `cancelPan()` 立刻接管；`prefers-reduced-motion` 下直接跳转。
- 线路按钮点击后先由业务层更新 `aria-pressed`，再 `focusRouteSpots()` 取选中组点位的包围盒中心派发居中事件；只用包围盒而不取质心，避免个别远端点位把中心拽偏。编辑模式拖动点位**不**重新居中（`guide:spots-changed` 只重算高亮），否则拖一个点视野会跟着跑。
- 行程卡片组与 G1–G9 是严格一一对应：`sync()` 只显示 `chosen` 命中的组，未选为空并显示 `#guideCardsEmpty` 占位（仅 route 模式；map 模式仍是导览引导占位）。`itineraryText()` 只导出 `.gc-route:not(.gc-hidden)`，因此分享内容与所见一致。
- stdout 为用户可见正文（页面路径、按片区清单、文字行程单），stderr 为运行元数据（来源、热区／线路数、sha256 前 16、预览 403 提示、接口与图片统计）。禁止打印 base64、接口原始大 payload 或任何 PII。

## 资源

- `assets/spots.json`：景点唯一数据源（名称、类型、简介、坐标、片区、所属线路），数组顺序即编号；生成器据此渲染热区、线路按钮与页内数据块。
- `assets/wuhan-guide-map.html`：唯一单页模板（约 180KB）。内置 `spots.json` 当前快照对应的热区与线路按钮、内联数据与导览占位，**直接双击/预览即可完整使用**（底图取同目录的 `wuhan-guide-map.jpg`）；可拖动平移的竖版底图、G1–G9 多选筛选、弹窗、景点编辑工具条与属性面板、底部固定展开的行程区（每组一张卡片）均在此文件内；无 CDN、无外链。
- `assets/wuhan-guide-map.jpg`：外置底图（1400×1592，JPEG q80，约 850KB）。由原 1920×2184 底图降采样重编码而来；改图后须同步模板 `<img class="map-art">` 的 `width`/`height`。
- `scripts/guide_common.py`：唯一渲染契约与共享工具。令牌/块标记常量、`load_spots()`（校验名称唯一／坐标 0–100／线路合法）、`route_spots()`、`render_spots_html()`／`render_route_btns()`／`render_spots_json()`、`spots_digest()`、`load_template()`、`render_page()`（块替换 + 精确替换 + 临时文件 + `os.replace` 原子写）、`render_list()`／`preview_hint`／`page_digest`，两个入口共用。
- `scripts/show_map.py`：导览模式薄入口，零网络、零接口，注入引导占位与 `map` 模式。
- `scripts/query_route.py`：线路模式入口。保留 `fetch_records()`／`normalize()`／`build_thumbs()`／`render()` 与全套 CLI（`codes`／`--days`／`--find`／`--all`／`--exclude`／`--replace`／`--half`／`--hours`／`--area`／`--theme`／`--no-sort`／`--no-image`／`--out`）；`render_card_fragment()` 只返回作用域化 CSS 与卡片片段（每条线路一个 `section.gc-route[data-route]`，标题为「Gx · 线路名」），交给 `guide_common.render_page()` 注入同一模板。图片默认并发预取后 base64 内联，单张内联失败则省略该图并给出占位说明，页面不产生任何外链请求；`--no-image` 可切换轻量模式。
- `references/route_codes.md`：代号字典、衔接链、N 日游推导表、景点→代号速查；仅作零调用文字快答字典，不含接口 13 字段明细，不能替代接口数据。
- `references/api_reference.md`：接口地址、请求体、响应结构、错误码与环境变量，排查调用问题时查阅。
