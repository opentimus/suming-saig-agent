---
name: natural-answers-and-guide-adapt
overview: 让专家回答自然、快速且不暴露内部引用；并在 wuhan-guide 现有 query_route.py 上以最小增量新增「排除/替换景点、半天/自定义时长、按片区/主题筛选」三类向后兼容能力，同步 Agent 与 SKILL.md 文档。
todos:
  - id: natural-answers
    content: 重写 Agent 与 saig-spu-rag 技能：自然简洁作答、去掉固定模板与内部引用
    status: completed
  - id: extend-guide-cli
    content: 在 query_route.py 新增 exclude/replace/half/hours/area/theme 三类可选能力
    status: completed
  - id: update-guide-docs
    content: 用 [skill:skill-creator] 更新 wuhan-guide 文档并同步 Agent 路由与最小适配原则
    status: completed
    dependencies:
      - natural-answers
      - extend-guide-cli
  - id: verify-changes
    content: py_compile 与 --help 校验，pack --list 通过，并按需冒烟新参数
    status: completed
    dependencies:
      - update-guide-docs
---

## 产品概述

让「鲸小武」城市AI接待员回答更自然、更快、且不暴露内部引用；同时在不重写的前提下，为 wuhan-guide 的线路规划脚本补充三类向后兼容的小幅能力，覆盖更多旅游规划诉求。

## 核心特性

- 回答风格自然化：去掉固定「五段式模板」与每次结尾强行追加的「2-3 个可深入方向」，按需自然作答、先答后补。
- 不显示内部引用：对用户不出现文件名、章节、页码、「知识库」标签或检索过程；检索仅用于内部保证准确。
- 更快的响应：优先一次调用、减少不必要的串联，检索候选数下调。
- wuhan-guide 三类小幅扩展（均为可选参数，默认行为不变）：
- 排除或替换景点/线路（如「不去黄鹤楼」「把东湖换成汉街」）。
- 半天或自定义时长（如「半天」「3 小时」，按整条线路裁剪行程组合）。
- 按片区或主题偏好筛选（如「从汉口出发」「亲子/夜景」）。
- 文档同步：Agent 路由与 wuhan-guide 技能说明补充新参数与「最小适配、禁止大改」原则。

## 技术栈

- Python 3 标准库（argparse、re 等），无新增第三方依赖。
- 文档为 Markdown；wuhan-guide 复用现有模板与渲染链路。
- 现有数据字段：code、order、spot、kind、duration、stars、review、area、img1..3。

## 实现思路

### 需求1：回答自然、快速、无内部引用

修改 `agents/jing-xiao-wu.md`：

- 核心能力与路由表中删除「返回带来源/章节/页码的证据块，供作答引用」等表述，改为「检索仅用于内部核对，对用户自然作答」。
- L0 快答：删除固定五段式模板与强制「2-3 个可深入方向」；改为「直接、口语化、简洁作答，先给结论再补必要细节；信息不足或可延续时再自然提示」。
- 输出规范：删除「标注来源」条目；保留忠实事实、自然措辞的边界说明、错误透明。
- 检索调用候选数由 `6` 下调到 `4`，坚持单次调用、避免同轮串联。

修改 `skills/saig-spu-rag/SKILL.md`：

- description/Overview 去掉「供作答时引用」口径，改为「检索用于内部保证准确，不向用户展示来源」。
- 使用步骤第 4 步改为「仅以检索内容为事实依据、用自己的话自然作答，不提及文件名、章节或检索过程」。
- 字段说明保留（source/section/page 仅供内部核对），`retrieve.py` 输出结构不改。

### 需求2：query_route.py 三类最小增量

仅新增可选参数与小函数，复用 `fetch_records`、`normalize`、`render`、`render_card_fragment`、`gc.render_page`，不改抓取、归一化、模板。

新增参数（全部可选、向后兼容）：

- `--exclude`（可重复，支持逗号/顿号分隔）：若为线路代号（G1-G9）则从目标线路中移除；否则按景点名子串剔除。
- `--replace OLD=NEW`（可重复）：在所选线路内，用数据集中已存在的 NEW 替换 OLD，保持原位置与所属代号；NEW 不存在则 stderr 警告并跳过。
- `--half`：等价 `--hours 4`。
- `--hours H`：按线路规范顺序累计各线 `parse_hours` 时长，保留预算内的线路（至少保留 1 条），超出部分提示。
- `--area`（可重复）：按 `area` 子串筛选（如 汉口）。
- `--theme`（可重复）：按 `kind`、`spot`、`review` 子串筛选（如 亲子、夜景、美食）。

主流程接入顺序（`main()` 内、渲染之前）：

1. `records = normalize(rows)`。
2. 按 all/days/find/codes 得到 `target_codes`（`--find` 仍用全量记录反查）。
3. 应用 `--replace`（以全量记录查找 NEW）。
4. 应用 `--exclude`（代号移除 + 景点过滤）。
5. 应用 `--area`、`--theme` 过滤。
6. 剔除过滤后为空的线路，保持顺序。
7. 应用 `--hours`/`--half` 线路级裁剪。
8. 复用 `render` 与 `render_card_fragment` 输出文字行程单与单页。

```mermaid
flowchart LR
  A[fetch_records] --> B[normalize]
  B --> C[选定 target_codes]
  C --> D[replace]
  D --> E[exclude]
  E --> F[area/theme]
  F --> G[去空线路]
  G --> H[hours 裁剪]
  H --> I[render + render_card_fragment]
```

边界与兼容：

- 无基础选择但给了 `--hours/--half` 时，默认 `codes_for_days(1)` 再裁剪。
- 仅有筛选类参数而无基础选择时，默认 `--all` 再筛选。
- 过滤/替换后为空则清晰报错退出，不崩溃、不覆盖既有页面。
- 所有新参数缺省时，行为与当前完全一致。

### 文档同步

- `skills/wuhan-guide/SKILL.md`：模式 B 补充新参数示例，并写入「优先映射现有参数；确需扩展时在现有函数上做最小增量、复用 fetch/normalize/render/模板，禁止重写」原则。
- `agents/jing-xiao-wu.md` 路由：补充新参数示例，强调「其他规划需求最小适配」。

## 性能与可靠性

- 过滤/裁剪为 O(记录数)，百级规模，开销可忽略；仍保持单次接口调用，新参数不触发额外请求。
- 空结果、无效 `--replace` 格式、预算不合理等均以 stderr 明确提示，退出码非零但不破坏产物。
- `--find` 反查不受过滤影响，避免语义漂移。

## 目录结构（本次改动）

- `agents/jing-xiao-wu.md` [MODIFY]：回答风格自然化、去内部引用、补新参数示例与最小适配原则。
- `skills/saig-spu-rag/SKILL.md` [MODIFY]：检索内部化、自然作答口径。
- `skills/wuhan-guide/scripts/query_route.py` [MODIFY]：新增 exclude/replace/half/hours/area/theme 可选参数与小函数，复用现有链路。
- `skills/wuhan-guide/SKILL.md` [MODIFY]：新参数说明与最小适配原则。
- 不改动：`guide_common.py`、`assets/wuhan-guide-map.html`、`assets/spots.json`、`saig-spu-rag/scripts/retrieve.py`、`tools/gen_route_docs.py`、`tools/pack_expert.py`。

## Agent 扩展

### Skill

- **skill-creator**
- 用途：按技能编写最佳实践更新 `skills/wuhan-guide/SKILL.md`，确保 frontmatter、参数说明、最小适配原则结构规范。
- 预期结果：产出与现有 `query_route.py` 一致、可被 Agent 正确调用的技能文档。