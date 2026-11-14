---
name: wuhan-panorama-guide
overview: 新增 wuhan-panorama-guide 技能（触发语「武汉全景导览」），内置修好焦点对齐的交互地图 HTML；同时修复原地图热区偏移的两处根因：GSAP 覆盖 CSS 居中位移、热区百分比坐标为估值。
---

## 需求拆解

1. **新增技能 `wuhan-panorama-guide`（武汉全景导览）**：当用户表达「武汉全景导览」意图时调用，输出一张可直接预览的交互地图 HTML + 按片区整理的景点清单。用户已确认：

- 地图文件作为 skill 的**单一源文件**内置在 `skills/wuhan-panorama-guide/assets/`，运行时复制到工作区并回显预览路径；
- L0 档位**只给地图 + 简短清单**，不生成解说词，不调用任何知识库接口。

2. **修复地图焦点（热区）未对齐景点**：仅修正现有 17 个热区的对齐问题，**不新增**热区（图上另有江汉路步行街、黎黄陂路、武商梦时代、华中科技大学、武汉理工大学、汉口站、武昌站、武汉站、天河机场、月湖·宝岛台、龟山·晴川阁等标签本次不做）。

## 验收标准

- 在浏览器中打开生成的 `wuhan-panorama.html`，17 个热区的可点击框分别压在对应「照片圆牌 + 白色胶囊标签」上；缩放（0.85x–1.55x）、窗口 resize、夜间模式、鼠标倾斜（rotationX/rotationY）后仍对齐。
- 点击任一热区，弹窗标题/分类/描述为该景点自己的文案；关闭后焦点回到该热区。
- 技能触发语「武汉全景导览」可稳定命中该技能，且只执行 1 次脚本调用。
- 地图离线可用（不依赖 CDN）。

## 边界

- 不改景点文案、不新增景点、不改视觉风格与工具栏功能。
- 不做「点到点导航/实时信息」类扩展。
- 不引入构建脚本（用户未选「动态生成」方案）。

## 目标文件与现状

| 对象 | 路径 | 现状 |
| --- | --- | --- |
| 地图源文件 | `/Users/wanbarry/Downloads/wuhan_gsap_interactive_map.html` | 240 行 / 2.7MB；`<img class="map-art">` 内联 base64 PNG（2,013,575 B，1536×1024）；GSAP 走 CDN（第 7 行） |
| 新技能目录 | `skills/wuhan-panorama-guide/` | 不存在 |
| 技能注册 | `.codebuddy-plugin/plugin.json` → `skills` 数组 | 现有 5 项 |
| Agent 路由 | `agents/jing-xiao-wu.md` | 「核心能力」5 条、「工作流程（按问题路由）」表格、分流原则 |
| 说明文档 | `README.md` 「功能」列表 | 5 条 |


## 关键技术决策

1. **放弃 CSS `transform` 居中，改用纯布局居中**
```css
/* 现状（冲突源） */
.hotspot{ left:var(--x); top:var(--y); transform:translate(-50%,-50%); }
/* 改为 */
.hotspot{
--w:9%; --h:14%;
left:calc(var(--x) - var(--w) / 2);
top:calc(var(--y) - var(--h) / 2);
width:var(--w); height:var(--h);
}
```
理由：GSAP 的 `y/scale/z` 会把整条 `transform` 重写为 px 值，`translate(-50%,-50%)` 的百分比语义随之丢失；`left/top` 用 `calc` 布局居中后，`transform` 完全交给 GSAP，二者不再争夺同一属性，且无浏览器兼容成本（优于 `translate` 独立属性的 Safari 14.1+ 要求）。

2. **GSAP 3.12.5 内联**，移除 CDN `<script src>`，保留 `/*! GSAP 3.12.5 */` 许可头。当前脚本头部有 `if (!window.gsap) { warn; return; }` 早退，CDN 不可达时热区点击会整体失效，因此必须内联。GSAP 来源：优先从 `cdnjs` 取 3.12.5 官方文件；离线时使用既有 `/tmp/gsap.min.js`（72,214 B，版本横幅已核对为 3.12.5），实现时记录 sha256 以固定来源。

3. **取消热区本体的 `y` 轴浮动动画**（`gsap.to(pin,{y:-3,repeat:-1,yoyo:true})`）。这是「看起来没对准」的第二重观感来源：热区会在标签上持续上下漂移 3px。浮动改为不作用于热区盒子本身，hover 只保留 `scale`，去掉 `z:24`（3D 抬升会让热区相对标签产生透视位移）。

4. **重叠区用 `z-index` 收口**：`湖北省博物馆 / 武汉SKP / 武汉大学` 三者矩形在 1536×1024 上有 3–6 个百分点交叠，DOM 顺序决定命中优先级。给 `.hotspot:hover / :focus-visible / .is-active` 提升 `z-index`，并在 `openDetail()` 中补上 `is-active` 类（现 CSS 已有 `.hotspot.is-active::before` 规则但 JS 从未添加该类，属死代码，顺手接通；`closeDetail()` 移除）。

5. **运行期交付脚本**而非静态路径：新增 `scripts/show_map.py`，`shutil.copyfile` 到工作区 ASCII 文件名 `wuhan-panorama.html`，复用 `skills/wuhan-route-query/scripts/query_route.py:620-633` 的 `NON_PREVIEWABLE_ROOTS` / `_preview_hint` 约定（预览服务只服务工作区，`/tmp` 会 403）。零网络请求、幂等覆盖、退出码非 0 即失败。

## 风险与权衡

- **仓库体积 +2.7MB 二进制**：可接受（单文件、离线、无外链图表）；若后续要瘦身，可另做 `--compress-image`（本次不做）。
- **编辑 2.7MB 单行 base64 文件**：必须用 Python 做精确字符串替换（定位 `<script src=...></script>` 与 17 段 `style="--x:.."`），不得整文件重排或统一行尾，否则可能破坏 base64 行或引入巨大 diff。
- **热区矩形较高**（覆盖圆牌 + 胶囊，高约 14%）：hover 高亮环会是竖长圆角矩形，观感可接受；若显拥挤只调 `border-radius`，不改几何。