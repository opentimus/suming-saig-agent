---
name: wuhan-guide 景点悬停发光效果移除
overview: 移除地图景点悬停时热区后面的白色发光底与标签橙色光圈，仅保留 1.07 倍轻微放大；编辑模式悬停保留虚线框但去掉发光外圈，重新生成页面并做悬停视觉验收。
todos:
  - id: tune-hover-css
    content: 调整普通态与编辑态悬停规则：移除发光底与橙色光圈，保留放大、基础阴影和虚线提示
    status: completed
  - id: regen-page
    content: 运行 show_map.py 重新生成工作区 wuhan-guide.html
    status: completed
    dependencies:
      - tune-hover-css
  - id: verify-hover
    content: 使用 [skill:playwright-cli] 悬停景点核对伪元素样式、选中态与编辑态并截图
    status: completed
    dependencies:
      - regen-page
---

## 用户需求

取消地图景点图标在鼠标悬停时出现的「发光背景」效果，让悬停反馈更克制。

## 产品概述

仅调整景点标签的悬停视觉，不改动地图布局、景点数据、筛选与编辑逻辑；页面其他部分保持现状。

## 核心功能

- 普通悬停：移除热区后方半透明白色发光底，移除标签周围的橙色光圈；仅保留标签 1.07 倍轻微放大、轻微底色变化与基础投影。
- 选中态：打开详情弹窗或属性面板时的景点高亮（白色底 + 光晕 + 橙色光圈）保持不变，避免丢失选中反馈。
- 编辑模式：悬停仍显示橙色虚线框以提示可拖拽，但不再显示发光外圈；编辑态选中高亮保持不变。
- 键盘聚焦：保留原有橙色 outline，无障碍焦点提示不受影响。

## 技术栈

- 单文件 HTML + 内联 CSS + 原生 JS（现有 `skills/wuhan-guide/assets/wuhan-guide-map.html`）。
- Python 渲染契约 `guide_common.py`，入口 `show_map.py` 重新生成页面。
- 浏览器验收：`playwright-cli`。

## 实现方案

只改 CSS，不动 JS 与数据，属于纯视觉降噪。

### 关键改动

1. **普通悬停底光**：将现有合并规则
`.hotspot:hover::before, .hotspot:focus-visible::before, .hotspot.is-active::before`
拆分为仅 `.hotspot.is-active::before`，保留选中态的白色发光底；悬停与键盘聚焦不再绘制 `::before` 背景、边框与 `box-shadow`（伪元素本身透明，视觉上完全消失）。
2. **标签橙色光圈**：把 `.hotspot:hover .spot-chip, .hotspot:focus-visible .spot-chip, .hotspot.is-active .spot-chip` 拆成两条：

- 悬停/聚焦：保留 `scale(1.07)`、浅暖白渐变底色、白色描边和基础投影 `0 8px 22px rgba(31,74,99,.32)`，去掉 `0 0 0 3px rgba(242,174,76,.45)` 光圈；
- `.is-active`：沿用原值（含橙色光圈），保持选中态强度。

3. **编辑态悬停**：将
`.map-shell.is-editing .hotspot:hover::before, .map-shell.is-editing .hotspot.is-active::before`
拆分：悬停仅把虚线描边提亮为 `rgba(230,154,50,.95)`，不加实线、不加背景与 `box-shadow`；`.is-active` 保留原有实线白框 + 光晕。
4. GSAP 的 `scale:1.04` hover 动画与 `z-index:6` 命中优先级保持不变，避免悬停时的层级与手感回退。

### 性能与可靠性

- 纯 CSS 属性删减，无新增选择器层级与运行时开销；不触发额外重排。
- 模板约 2.4MB 且含单行 base64，全部使用精确字符串替换，禁止格式化与行尾统一。
- 选中态规则独立保留，防止把「悬停降噪」误伤为「选中反馈消失」。

## 实现注意事项

- 不要删除 `.hotspot:focus-visible{outline:2px solid #df8e2e}`，键盘可达性依赖它。
- 不要改动 `.hotspot.is-dimmed` 与 `.hotspot.is-matched` 相关规则。
- 修改后必须用 `show_map.py --out /Users/wanbarry/suming-saig-agent/wuhan-guide.html` 重新生成产物，模板改动才会生效。
- 验收时用 `getComputedStyle(pin, "::before").boxShadow` 断言悬停为 `none`、`.is-active` 仍有光晕；同时确认景点仍为 18 个、console 无报错。

## 目录结构

```
skills/wuhan-guide/assets/
└── wuhan-guide-map.html   # [MODIFY] 拆分普通态/编辑态悬停规则：移除 ::before 发光底与标签橙色光圈，保留选中态
wuhan-guide.html           # [REGENERATE] 由 show_map.py 重新生成的交付页面
```

### Skill

- **playwright-cli**
- Purpose: 在本地 HTTP 服务上打开重新生成的页面，悬停景点并截图核对视觉，同时读取伪元素计算样式。
- Expected outcome: 悬停态 `::before` 无 box-shadow/背景、标签无橙色光圈；选中态与编辑态虚线仍正常；18 个景点不变、console 无报错。