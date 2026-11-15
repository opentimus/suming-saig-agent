---
name: wuhan-guide-page-performance
overview: 优化武汉导览单页的运行时性能：底图从 HTML 内联 base64 改为外置图片并按需加载/重编码，移除 3D 倾斜交互，降低 44 个景点标签的模糊合成开销，并把线路 SVG 从全量重建改为增量更新。
---


## 用户需求

用户提出两条诉求（原话）：

> 1、当在地图上选中组的时候，自动切换到地图上关联景点的中心。
> 2、组要与景点列表联动。即：没有关联组的时候列表为空，关联G1就展示G1的，关联G1+G2就展示G1+G2。

经结构化提问澄清，用户明确答复三点：

| 问题 | 用户选择 |
| --- | --- |
| 「景点列表」范围 | **只要行程卡片组** —— 仅改线路查询模式（`route`）下的 `.gc-route` 卡片组；导览模式（`map`）底部引导占位**不变** |
| 取消全部选中时地图视野 | **保持不动** —— 地图停在当前位置，**不**回到初始视图 |
| 居中方式 | **平滑动画** —— 约 400ms 滑到关联景点中心 |

## 验收标准

1. 点击 G1 按钮 → 地图在约 400ms 内平滑移动到 G1 六个点位的包围盒中心。
2. 再点 G2 → 视图重新居中到 G1+G2 并集的包围盒中心。
3. 取消某个组（集合仍非空）→ 按剩余组重新居中；全部取消 → 视图**完全不移动**。
4. 线路模式产物：未选任何组时 `.gc-route` 全部隐藏、显示空占位提示；选 G1 只显示 G1 卡片组；选 G1+G2 同时显示两组。
5. 导览模式（`map`）底部引导占位文字与视觉保持现状。
6. 性能契约不回退：拖动期 `is-panning` 降级、`measure()` 缓存、`scheduleApply()` 合并写入、线路 SVG 增量更新均继续生效。
7. 页面体积不显著回升（当前 HTML 174KB + 底图 850KB）。



## 现状定位

主改动文件：`skills/wuhan-guide/assets/wuhan-guide-map.html`（174KB，纯 LF）

### 三处需要协作的代码

**① 点位高亮筛选（业务 IIFE，`wuhan-guide-map.html:725-752`）**

```js
function applyRoutes(){
  const routeBtns = gsap.utils.toArray(".route-btn");
  const chosen = routeBtns.filter(b => b.getAttribute("aria-pressed") === "true");
  const matched = new Set();
  chosen.forEach(b => (b.dataset.spots || "").split(",").forEach(no => { if(no) matched.add(no.trim()); }));
  ...
}
routeWrap.addEventListener("click", e => {
  const btn = e.target.closest(".route-btn");
  if(!btn) return;
  btn.setAttribute("aria-pressed", ...);
  applyRoutes();
});
document.addEventListener("guide:spots-changed", applyRoutes);
```

关键：`applyRoutes()` 同时被「用户点击」与「编辑模式重建」两条路径调用，需要区分是否应触发居中。

**② 卡片组过滤（抽屉 IIFE，`wuhan-guide-map.html:877-896`）**

```js
function sync(){
  const chosen = pressedCodes();
  blocks.forEach(sec => {
    const hit = chosen.length === 0 || chosen.indexOf(sec.getAttribute("data-route")) >= 0;  // ← 需改
    sec.classList.toggle("gc-hidden", !hit);
  });
  if(GUIDE_MODE === "route"){
    hint.textContent = chosen.length ? "已按上方选择过滤行程卡片与地图点位" : "按上方 G1–G9 筛选行程卡片 · 共 " + blocks.length + " 组";
  }else{ /* map 模式文案保持不变 */ }
}
```

**③ 地图平移（独立 vanilla IIFE，`wuhan-guide-map.html:759-856`）**

```js
let px = 0, py = 0;
let minX = 0, minY = 0;
function measure(){
  minX = Math.min(0, shell.clientWidth - canvas.offsetWidth);
  minY = Math.min(0, shell.clientHeight - canvas.offsetHeight);
}
function apply(){ canvas.style.transform = "translate3d(" + px + "px," + py + "px,0)"; }
function scheduleApply(){ if(frame) return; frame = requestAnimationFrame(() => { frame = 0; apply(); }); }
function moveTo(x, y, immediate){ px = clamp; py = clamp; if(immediate) apply(); else scheduleApply(); }
function resetView(){ measure(); moveTo(minX / 2, 0, true); }
```

`px/py` 为闭包私有，该 IIFE 未对外暴露任何接口。

### 技术方案

#### 1. 跨 IIFE 通信：沿用既有自定义事件风格

项目已有 `document.dispatchEvent(new CustomEvent("guide:spots-changed"))` 作为解耦手段（编辑 IIFE → 业务 IIFE）。新增两个事件，**不引入全局变量**：

| 事件 | 派发方 | 载荷 | 消费方 |
| --- | --- | --- | --- |
| `guide:routes-changed` | 业务 IIFE（仅用户点击时） | 无（消费方自行读 DOM） | 平移 IIFE（居中）、抽屉 IIFE（列表联动） |
| `guide:focus-bounds` | 业务 IIFE | `{x, y}` 底图百分比中心点 | 平移 IIFE（执行动画） |

选择理由：
- 与 `guide:spots-changed` 命名风格一致，无需在 `window` 上挂 `__guidePanTo` 之类的隐式契约；
- 平移 IIFE 因此**不依赖任何数据源**（不需要读 `#guideSpotsData`，也不需要知道 `data-spots` 格式），职责最纯；
- 派发点集中在 `routeWrap` 的 click 处理器内，与 `applyRoutes()` 同步完成，不存在监听器注册顺序问题（现状是两个独立 `click` 监听，靠 DOM 顺序保证 `aria-pressed` 已更新，脆弱）。

**关键：仅「用户点击」派发 `guide:routes-changed`**。`document.addEventListener("guide:spots-changed", applyRoutes)` 这条路径上**不派发**，避免编辑模式拖动点位时视图跟着跑。

#### 2. 居中目标点：包围盒中心而非质心

选中组可能包含远端点位（如 G2 的「光谷步行街」x=91.3 与「广八路」x=73.6），质心会被点数分布拉偏；包围盒中心 `((minX+maxX)/2, (minY+maxY)/2)` 更稳定，且能保证所有关联点位尽量落在视口内。

计算放在业务 IIFE 内（它已持有 `matched` 集合与热区节点）：

```js
function routeBoundsCenter(matched){
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  matched.forEach(no => {
    const pin = layer.querySelector('.hotspot[data-no="' + no + '"]');
    if(!pin) return;
    const x = parseFloat(pin.style.getPropertyValue("--x"));
    const y = parseFloat(pin.style.getPropertyValue("--y"));
    if(!isFinite(x) || !isFinite(y)) return;
    if(x < minX) minX = x;
    if(x > maxX) maxX = x;
    if(y < minY) minY = y;
    if(y > maxY) maxY = y;
  });
  if(minX === Infinity) return null;
  return { x: (minX + maxX) / 2, y: (minY + maxY) / 2 };
}
```

复用 `--x`/`--y`（热区自身就是这两个变量的消费方），无需解析 `#guideSpotsData`，编辑模式下坐标改动也会自然反映（因为 `refreshPin()` 会写回这两个变量）。

#### 3. 平移 IIFE 新增：尺寸缓存 + 反算 + 动画

**a. 扩充 `measure()` 缓存画布尺寸**，避免每次居中读 `offsetWidth`（一次强制布局可接受，但缓存后连续点击更省）：

```js
let canvasW = 0, canvasH = 0;
function measure(){
  canvasW = canvas.offsetWidth;
  canvasH = canvas.offsetHeight;
  minX = Math.min(0, shell.clientWidth - canvasW);
  minY = Math.min(0, shell.clientHeight - canvasH);
}
```

**b. 百分比 → 平移量反算**（让目标点落在视口正中）：

```js
function centerOn(xPercent, yPercent){
  if(canvasW <= 0 || canvasH <= 0) measure();
  const targetX = shell.clientWidth / 2 - canvasW * xPercent / 100;
  const targetY = shell.clientHeight / 2 - canvasH * yPercent / 100;
  return { x: Math.max(minX, Math.min(0, targetX)),
           y: Math.max(minY, Math.min(0, targetY)) };
}
```

**c. 400ms 补间**（`requestAnimationFrame` + easeOutCubic，与页面既有 GSAP `power2.out` 手感接近）：

```js
let animFrame = 0;
function cancelAnim(){
  if(!animFrame) return;
  cancelAnimationFrame(animFrame);
  animFrame = 0;
  document.documentElement.classList.remove("is-panning");
  canvas.classList.remove("is-panning");
}
function animateTo(tx, ty, duration){
  cancelAnim();
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if(reduce || duration <= 0){ moveTo(tx, ty, true); return; }
  const sx = px, sy = py, t0 = performance.now();
  canvas.classList.add("is-panning");          /* 动画期同样降低标签 blur 合成开销 */
  document.documentElement.classList.add("is-panning");
  const step = now => {
    const t = Math.min(1, (now - t0) / duration);
    const e = 1 - Math.pow(1 - t, 3);          /* easeOutCubic */
    moveTo(sx + (tx - sx) * e, sy + (ty - sy) * e, true);
    if(t < 1){ animFrame = requestAnimationFrame(step); }
    else { animFrame = 0; canvas.classList.remove("is-panning"); document.documentElement.classList.remove("is-panning"); }
  };
  animFrame = requestAnimationFrame(step);
}
```

**d. 中断保护**：`pointerdown` 与键盘方向键前调用 `cancelAnim()`，避免动画与用户输入抢 `px/py`：

```js
shell.addEventListener("pointerdown", e => { cancelAnim(); ... });
shell.addEventListener("keydown", e => { ... cancelAnim(); moveTo(px + dx, py + dy); });
```

**e. 事件订阅**（在平移 IIFE 末尾）：

```js
document.addEventListener("guide:focus-bounds", e => {
  const d = e.detail || {};
  if(!isFinite(d.x) || !isFinite(d.y)) return;
  measure();                                   /* 视口/画布尺寸可能已变 */
  const target = centerOn(d.x, d.y);
  animateTo(target.x, target.y, 400);
});
```

取消全部选中时业务层**不派发**该事件，视图自然保持不动（满足用户第 2 条澄清）。

#### 4. 列表联动：未选即空

`sync()` 判断改为：

```js
const hit = chosen.length > 0 && chosen.indexOf(sec.getAttribute("data-route")) >= 0;
```

**空态占位**：由 `query_route.py` 的 `render_card_fragment()` 在卡片片段末尾追加 `<div class="gc-empty" hidden>…</div>`，抽屉脚本用 `hidden` 切换。放在渲染侧而非模板侧的原因：导览模式（`map`）注入的是 `intro_html()`，不含 `.gc-route`，也不该出现空占位——放在 `query_route.py` 里天然只影响线路模式。

```js
/* sync() 内 */
const emptyEl = document.getElementById("guideCardsEmpty");
if(emptyEl) emptyEl.hidden = chosen.length > 0;
```

占位文案与样式（新增到 `query_route.py` 的作用域化 CSS）：

```css
.gd-cards .gc-empty{margin:4px 0;padding:22px 16px;border:1px dashed rgba(43,127,184,.35);
  border-radius:14px;text-align:center;font-size:12.5px;line-height:1.8;color:#6c8496;
  background:rgba(255,255,255,.6)}
```

文案：「尚未选择线路 · 点上方 G1–G9 查看对应行程卡片（可多选）」

**`#guideDrawerHint` 文案**（仅 `route` 模式改动）：

```js
hint.textContent = chosen.length
  ? "已显示 " + chosen.length + " 条线路的行程卡片"
  : "未选择线路 · 点上方 G1–G9 查看行程";
```

`map` 模式分支完全保持现状。

#### 5. 触发链路

```js
/* 业务 IIFE */
routeWrap.addEventListener("click", e => {
  const btn = e.target.closest(".route-btn");
  if(!btn) return;
  btn.setAttribute("aria-pressed", btn.getAttribute("aria-pressed") === "true" ? "false" : "true");
  applyRoutes();
  document.dispatchEvent(new CustomEvent("guide:routes-changed"));   /* 新增 */
  const center = routeBoundsCenter(currentMatched());                 /* 集合非空才算 */
  if(center) document.dispatchEvent(new CustomEvent("guide:focus-bounds", { detail: center }));
});
```

`currentMatched()` 抽成小函数，供 `applyRoutes()` 与居中复用，避免重复解析 `data-spots`。

抽屉 IIFE 的列表联动改为监听事件，并保留一份兼容的 click 监听（`sync()` 幂等，重复调用无害）：

```js
document.addEventListener("guide:routes-changed", sync);
routeWrap.addEventListener("click", e => { if(e.target.closest(".route-btn")) sync(); });
```

编辑模式拖动点位（`guide:spots-changed`）不派发 `guide:focus-bounds`，视图不跟着跑。

#### 6. 文档同步（必须，否则文档与实现矛盾）

- `skills/wuhan-guide/SKILL.md:33`：「多选时只显示命中组、**未选时显示全部**」→ 改为「未选时列表为空并提示」
- `skills/wuhan-guide/SKILL.md:99`：「**未选线路时展示全部 9 张卡片**」→ 改为「未选线路时卡片区为空并显示引导占位」
- 同处补充：「选中线路后视图平滑居中到该组点位的包围盒中心（约 400ms）；取消全部选中时视图保持不动」
- `skills/wuhan-guide/SKILL.md` 第 137 行的拖动说明补充：`pointerdown` 会中断进行中的居中动画

#### 7. 分享按钮的一致性决策

`itineraryText()` 当前遍历 `blocks`（全部 9 组），不看 `.gc-hidden`。列表改为「未选即空」后，用户在空列表下点分享会得到全部 9 组，语义割裂。

**决定：改为只输出可见组**，一行改动：

```js
const visible = blocks.filter(sec => !sec.classList.contains("gc-hidden"));
if(!visible.length){ shareDone("先选线路"); return; }
const lines = ["武汉行程｜" + visible.length + " 组线路"];
```

理由：分享动作的直觉是「分享我正在看的内容」，与列表联动逻辑一致；`blocks` 仍为全量快照，不破坏编辑模式的增删逻辑。此项属需求外的小幅收敛，若后续不认可可单行回退。


# Agent Extensions
- [skill:playwright-cli]：用于浏览器端验证点击 G1/G2 后 `#mapCanvas` 的 `transform` 是否在约 400ms 内收敛到预期值、取消选中时是否保持不变，以及 `.gc-route` 的可见性与空占位切换。
