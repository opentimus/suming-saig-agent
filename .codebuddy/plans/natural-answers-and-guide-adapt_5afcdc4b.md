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
将新增的《2026 武汉旅游产品手册》纳入 `saig-spu-rag` 本地知识库，使其可被检索问答覆盖武汉文博场馆、四季赏花、都市漫游、红色旅游、演艺空间、乡村休闲、湖光山色、科技研学、长江游览、汉派美食、线路攻略及具体景点讲解等内容。

## 核心功能
- 新手册作为第 5 份数据源进入检索索引，与现有 4 份 Markdown 一并参与检索。
- 重建 `data/chunks.json` 与 `data/index.json`，使运行期检索能命中手册内容。
- 更新技能说明：描述、数据源清单、「何时使用」覆盖旅游产品手册类问题。
- 保持现有「检索仅供内部核对、不向用户展示来源、自然作答」口径不变。

## 视觉/交互
无界面变更，仅知识库内容与技能文档修订。


## 技术栈
- Python 3 标准库；沿用现有 Okapi BM25 检索（中文单字 + 二元组分词）。
- Markdown 数据源；无第三方依赖、无网络、无 subprocess。
- 技能目录结构保持不变：`SKILL.md` + `scripts/` + `references/` + `data/`。

## 实现思路
1. **无需改检索代码**：`build_index.py` 已自动扫描 `references/*.md`（并跳过 `sources.md`），`clean_markdown()` 会剥离 `![image](...)` 图片语法、把链接还原为文本、去掉 `<sup>/<sub>` 等 HTML 标签；`MD_HEADING_RE` 识别 `#`/`##` 标题，因此新手册会被自动分块与索引。
2. **重建数据**：运行 `python3 scripts/build_index.py`，重新生成 `data/chunks.json` 与 `data/index.json`，写入日志会列出每份数据源的块数，确认新手册已纳入。
3. **修订 `SKILL.md`（使用 skill-creator 规范）**：
   - `description` 增补「《2026 武汉旅游产品手册》」及文博/赏花/美食/演艺/研学/线路攻略等场景。
   - 「数据源」新增 `references/2026武汉旅游产品手册md.md` 一行，注明内容范围。
   - 「何时使用」新增旅游产品手册类触发场景（景点讲解、主题游线、文博场馆、赏花时节、汉派美食、演艺空间、科技研学、线路攻略等）。
   - 「references/」资源说明由「4 份」改为「5 份」。
   - 保持「检索仅供内部核对、不展示来源」口径不变。
4. **验证**：用「黄鹤楼」「武汉赏花」「汉派美食」「科技研学」「线路攻略」等样例调用 `retrieve.py`，确认命中 `source` 为 `2026武汉旅游产品手册md.md`；检查分块来源统计、`page` 均为 null；确认无绝对路径与 `sources.md` 残留；`tools/pack_expert.py --list` 通过。

## 性能与可靠性
- 构建期一次性 O(总 token 数)；运行期检索仍为毫秒级，新增约数百块不影响性能。
- 边界：若重建后块数异常或章节解析异常，仅做最小修正（如标题 OCR 噪声不影响检索，可不处理）。

## 目录结构（本次改动）
```
skills/saig-spu-rag/
├── SKILL.md                              # [MODIFY] description/数据源/何时使用/references 数量，纳入旅游产品手册
├── references/
│   └── 2026武汉旅游产品手册md.md          # [KEEP] 新增的第 5 份数据源（已存在）
├── scripts/
│   └── build_index.py                    # [KEEP] 自动扫描 references/*.md，无需改代码
└── data/
    ├── chunks.json                       # [REGENERATE] 重建后包含新手册分块
    └── index.json                        # [REGENERATE] 重建后的 BM25 倒排索引
```


## Agent Extensions
### Skill
- **skill-creator**
  - 用途：按技能编写最佳实践修订 `skills/saig-spu-rag/SKILL.md`，确保 frontmatter description、数据源、何时使用、资源说明结构规范一致。
  - 预期结果：产出一份准确覆盖 5 份 Markdown 数据源、触发场景完整、与现有「自然作答、不展示来源」口径一致的 SKILL.md。
