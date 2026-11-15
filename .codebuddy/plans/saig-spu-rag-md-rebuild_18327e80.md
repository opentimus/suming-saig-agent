---
name: saig-spu-rag-md-rebuild
overview: 将 saig-spu-rag 知识库改为直接以 references/ 下 4 份 .md 附件为唯一数据源重建索引，移除 sources.md 与 docx/pdf 绝对路径及 macOS 抽取工具依赖，使其可自包含对外发布。
todos:
  - id: rewrite-build-index
    content: 重写 build_index.py：扫描 references/*.md、Markdown 感知分块、移除绝对路径与 sources.md 生成
    status: completed
  - id: delete-sources-md
    content: 删除 references/sources.md
    status: completed
    dependencies:
      - rewrite-build-index
  - id: update-skill-md
    content: 用 [skill:skill-creator] 按新数据源重写 SKILL.md 文档口径
    status: completed
    dependencies:
      - rewrite-build-index
      - delete-sources-md
  - id: rebuild-index
    content: 运行 build_index.py 重建 data 索引并确认分块来源为 .md
    status: completed
    dependencies:
      - rewrite-build-index
      - delete-sources-md
  - id: verify-rag
    content: 样例查询验证检索、grep 确认无绝对路径/sources.md 残留、pack --list 通过
    status: completed
    dependencies:
      - update-skill-md
      - rebuild-index
---

## 用户需求

- 将 saig-spu-rag 的知识库数据源改为 `references/` 下新提供的 4 份 Markdown 附件（数命SPU说明.md、数命SPU社区说明.md、SAIG数命SPU国际AI大赛说明.md、武汉概览.md），直接引用这些 .md 文件。
- 禁止读取或依赖 `references/sources.md`，并移除与其相关的所有引用与生成逻辑。
- 技能要可自包含地对外发布：只用相对路径，不出现 `/Users/...` 绝对路径，不依赖 macOS 专有抽取工具（textutil/pdftotext/pdfinfo）。
- 保持现有检索脚本的调用方式与输出字段稳定，避免破坏 Agent 既有路由调用。

## 产品概述

saig-spu-rag 是「城市AI接待员」的本地知识库检索技能，覆盖数命SPU/社区、SAIG 国际AI大赛与《武汉概览》背景，运行期快速返回带来源与章节的证据块，供作答引用、避免编造。

## 核心特性

- 构建脚本自动扫描 `references/*.md`，按 Markdown 标题与内置段落标记分块，生成 `data/chunks.json` 与 `data/index.json`。
- 清理 Markdown 图片与外链语法，避免把 OCR 外链写入索引。
- 检索结果以 .md 文件名为来源、以章节标题为定位，页码统一为空；调用接口与输出字段保持不变。
- 删除 `sources.md`，并使 SKILL.md 文档口径与新数据源完全一致。

## 技术栈

- Python 3 标准库（os/re/json）：分块、BM25 索引与检索，无第三方依赖、无网络、无 subprocess。
- Markdown 文本以 UTF-8 直接读取；技能为插件内独立目录（SKILL.md + scripts + data + references）。

## 实现策略

1. 重写 `scripts/build_index.py`：

- 以脚本位置推导 `SKILL_DIR`，扫描 `references/*.md`（按文件名排序，防御性跳过 `sources.md`）作为唯一数据源，`source` 取文件名。
- 移除 `SOURCES` 硬编码绝对路径、`extract_docx`/`extract_pdf_pages`、`textutil/pdfinfo/pdftotext` 调用，以及写 `sources.md` 的逻辑。

2. Markdown 感知分块：

- 预处理：剥离 `![alt](url)` 图片语法；将 `[text](url)` 还原为 `text`（保留官方 URL 文本）。
- 章节识别在现有 `【】`/`第X章/节`/数字标题之外，新增 `^#{1,6}\s+` 标题（去 # 前缀）。
- 整篇无标题时，以文件名去扩展名作为 `section`（如「数命SPU说明」）。
- 沿用 `CHUNK_SIZE=520` 与超长句级重叠 1 句的滚动分块；chunk 字段保持 `source/section/page/text`，`page` 恒为 `None`。

3. 保持 BM25 索引结构与 `retrieve.py` 输出 `id/source/section/page/score/text` 不变；`retrieve.py` 仅更新 docstring，说明 md 无页码。
4. 删除 `references/sources.md`，清理 SKILL.md 中关于 sources.md、docx/pdf、「PDF 第几页」的表述，改为「来源文件 + 章节」口径。
5. 重建 `data/chunks.json` 与 `data/index.json`，并用样例查询验证来源为 .md 文件名。

## 关键技术决策

- 自动扫描替代硬编码清单：替换或新增附件无需改代码，契合对外发布时的自包含诉求。
- 纯标准库直接读 .md：跨平台、零安装、无绝对路径，彻底摆脱 docx/pdf 抽取工具。
- 保留 `page` 字段并置 null：兼容既有输出消费方，避免破坏 Agent 路由；文档明确 md 无页码。
- 不引入第二份数据源：`references/*.md` 仍是唯一事实源，`data/` 仍是唯一预构建产物。

## 性能与可靠性

- 构建 O(总 token 数) 一次；检索 O(查询词项×倒排表)，文档量约百块级，毫秒级返回。
- 边界：references 下无 .md 时明确报错退出；单文件读取失败告警并跳过；无命中沿用既有回退（标题包含→前 top_k）。

## 目录结构

```
skills/saig-spu-rag/
├── SKILL.md                        # [MODIFY] 数据源/引用口径改为 references/*.md，移除 sources.md、docx/pdf、页码表述
├── references/
│   ├── 数命SPU说明.md              # [KEEP] 数据源
│   ├── 数命SPU社区说明.md          # [KEEP] 数据源
│   ├── SAIG数命SPU国际AI大赛说明.md # [KEEP] 数据源
│   ├── 武汉概览.md                 # [KEEP] 数据源
│   └── sources.md                  # [DELETE] 旧清单（含失效绝对路径）
├── scripts/
│   ├── build_index.py              # [MODIFY] 扫描 .md、Markdown 分块、去绝对路径/subprocess/sources.md 生成
│   └── retrieve.py                 # [MODIFY] docstring 更新（md 无页码），逻辑与输出字段不变
└── data/
    ├── chunks.json                 # [REGENERATE] 由 .md 重建
    └── index.json                  # [REGENERATE] 由 .md 重建
```

## Agent Extensions

### Skill

- **skill-creator**
- Purpose: 更新 SKILL.md 时遵循技能编写最佳实践（frontmatter、触发条件、How to use/Notes/Resources 结构）。
- Expected outcome: 产出一份结构规范、描述准确、与 references/*.md 数据源一致的 SKILL.md。