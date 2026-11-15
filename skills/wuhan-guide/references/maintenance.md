# 武汉导览 · 维护约定

改景点数据、模板、脚本或页面交互前必读。日常问答与页面生成不需要这份文档。

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

## 页面结构与样式实现

- 景点坐标唯一维护在 `assets/spots.json` 的 `x/y/w`（中心百分比与宽度百分比）；生成器输出到热区 `style` 的 `--x/--y/--w`，`--h` 固定 88px。编号由数组顺序派生，浏览器内增删后自动重排；页面上改坐标只进 localStorage，不写回 JSON。标签由 `.spot-chip`（`.spot-no` + `.spot-name`）渲染，与底图同处 `.map-canvas`，用自身 `translate(-50%,-50%)` 居中，窄屏（≤650px）只显示编号牌。
- 9 个 `.route-btn` 的 `data-spots` 由每个景点的 `routes` 反推，是「线路 → 点位编号」唯一映射源；某条线路可以没有点位（`data-spots=""`）。多选时对并集点位加 `.is-matched`、其余加 `.is-dimmed`，只切 class，不触碰 `transform`。
- 地图编号牌的底色跟所属线路主题色一致：热区 `style` 注入 `--rc:var(--gN)`，`N` 取 `routes` 的第一条线路（如东湖 G2/G3 取 G2、龟山 G1/G6 取 G1），无线路的新增点位回退橙金 `#e69a32`；只染 `.spot-no` 编号块，名称胶囊保持白底玻璃质感。编辑模式切换线路时会同步改写 `--rc`。

## 缩略图缓存

线路模式的景点缩略图会落盘复用，目录为 `~/.cache/wuhan-guide/thumbs`：

- 键 = `sha256(图片URL + 缩略图尺寸 + JPEG 质量)`，改 `THUMB_SIZE`/`THUMB_QUALITY` 后旧图自动失效；
- 缓存根目录可用 `WUHAN_GUIDE_CACHE` 覆盖，清理直接删目录即可；
- 下载/缩放失败的 URL 会写 `!fail` 标记，7 天内不再重试（源站 403 的占位图不再每次白等超时）；
- `--no-cache` 跳过读写，用于排查「线上换了图但本地没变」；
- 总占用超过 300MB 时按访问时间自动淘汰到 240MB 以下。
