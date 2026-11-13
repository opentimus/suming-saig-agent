---
name: 回退工作区到 daa22f2
overview: 按用户确认的「直接全部丢弃」方案，用 git reset --hard HEAD 与 git clean -fd 将工作区恢复到唯一提交 daa22f2，随后验证工作区干净；此操作不可恢复，执行前不再做二次确认以外的动作。
todos:
  - id: precheck-worktree
    content: 只读复核 HEAD 与改动清单，确认无清单外新增文件
    status: completed
  - id: reset-and-clean
    content: 执行 git reset --hard HEAD 与 git clean -fd 丢弃全部改动
    status: completed
    dependencies:
      - precheck-worktree
  - id: verify-and-report
    content: 验证工作区干净、目录已移除并报告结果不可恢复
    status: completed
    dependencies:
      - reset-and-clean
---

## 用户要求

回退整个项目到 Git 最新版本（唯一提交 `daa22f2 chore: 初始化仓库，添加 agent 与技能包`），丢弃本次会话中所有未提交的改动与新增文件。用户已通过选项明确选择「直接全部丢弃」，并知晓改动永久不可恢复。

## 产品概述

一次性的工作区状态恢复。执行后仓库内容与初始提交完全一致，工作区无修改、无多余文件，不保留任何本次会话的多语种改造痕迹；不涉及功能开发与界面变更。

## 核心特性

- 范围：撤销 17 个已修改文件（+361 / −86 行），删除 6 个新增文件（`i18n.py`、四语语言包、校验脚本）及其目录
- 结果：工作区干净、与最新版本一致；改动不可恢复（无 stash、无提交）
- 边界：保留被忽略的本地文件，不改动仓库配置、不提交、不推送、不创建备份
- 保障：执行前复核工作区快照，执行后逐项验证并向用户报告结果

## 技术栈与执行环境

- 工作区：`/Users/wanbarry/suming-saig-agent`（macOS / zsh），Git 命令行
- 无第三方依赖、无构建步骤、无网络请求、无新增文件

## 实现策略

按「只读复核 → 破坏性命令 → 验证报告」三步顺序一次性完成，全程限定在该工作区内，避免中途停留造成状态不一致。

关键决策与权衡：

- `git reset --hard HEAD` 撤销 17 个已跟踪文件的修改；`git clean -fd` 删除 6 个未跟踪文件与 `locales/`、`scripts/` 目录。二者缺一不可：仅 reset 会残留新增文件，仅 clean 会残留修改。
- **不使用 `-x`**：保护 `.env`、`.venv/`、`__pycache__/` 等被 `.gitignore` 忽略的用户本地文件，缩小影响面。代价是 `py_compile` 产生的 `__pycache__/` 可能残留，需用户另行授权才清理，不擅自扩大删除范围。
- 不执行 stash、不建备份分支、不提交：用户已选择不可恢复的直接丢弃，任何备份都违背其意图。
- 不使用 force push、不修改 git config、不做 amend；本次无远端操作需求。

## 性能与可靠性

单次工作区遍历，复杂度 O(工作区文件数)，无循环、无重复扫描、无额外 I/O 峰值；命令为 Git 原生操作。主要风险是误删核查清单之外的新增文件，以执行前的只读复核作为安全闸门。

## 执行注意事项

- 复核时若出现核查清单之外的新增未跟踪文件，立即暂停并告知用户，不继续执行 clean。
- 输出仅包含命令结果摘要与验证结论，不回显任何凭据值或大段 diff。
- 验证四项：`git status --short` 为空、HEAD 仍为 `daa22f2`、未跟踪文件列表为空、`i18n.py` 与 `locales/`、`scripts/` 已不存在。
- 结论须明确告知：改动不可恢复，如需找回只能重新实现；被忽略的 `__pycache__/` 未清理。

## 目录结构（全部受影响文件）

说明：[MODIFY] 表示恢复为 `daa22f2` 版本，[DELETE] 表示删除本次新增的未跟踪文件；本计划不创建任何文件。

```
suming-saig-agent/
├── README.md                                        # [MODIFY] 恢复，移除「多语种」章节与进度说明
├── agents/jing-xiaowu.md                            # [MODIFY] 恢复，移除「语言规则」章节、输出规范与路由表改动
├── i18n.py                                          # [DELETE] 删除零依赖语言加载器
├── locales/
│   ├── zh.json                                      # [DELETE] 删除中文语言包，目录一并移除
│   ├── en.json                                      # [DELETE] 删除英文语言包
│   ├── ja.json                                      # [DELETE] 删除日文语言包
│   └── ko.json                                      # [DELETE] 删除韩文语言包
├── scripts/
│   └── check_locales.py                             # [DELETE] 删除语言包校验与 HTML 冒烟测试脚本，目录一并移除
└── skills/
    ├── saig-intro/
    │   ├── SKILL.md                                 # [MODIFY] 恢复档位协议引用与中文 query 表述
    │   ├── references/api_reference.md              # [MODIFY] 恢复环境变量表
    │   └── scripts/query_saig.py                    # [MODIFY] 恢复为原始版本，移除 --lang 与 argparse
    ├── shuming-spu-intro/
    │   ├── SKILL.md                                 # [MODIFY] 恢复档位协议引用与中文 query 表述
    │   ├── references/api_reference.md              # [MODIFY] 恢复环境变量表
    │   └── scripts/query_spu.py                     # [MODIFY] 恢复为原始版本，移除 --lang 与 argparse
    ├── wuhan-intro/
    │   ├── SKILL.md                                 # [MODIFY] 恢复档位协议引用与中文 query 表述
    │   ├── references/api_reference.md              # [MODIFY] 恢复环境变量表
    │   └── scripts/query_wuhan.py                   # [MODIFY] 恢复为原始版本，移除 --lang 与 argparse
    ├── wuhan-scenic-intro/
    │   ├── SKILL.md                                 # [MODIFY] 恢复档位协议引用与中文 query 表述
    │   ├── references/api_reference.md              # [MODIFY] 恢复环境变量表
    │   └── scripts/query_scenic.py                  # [MODIFY] 恢复为原始版本，移除 --lang 与 argparse
    └── wuhan-route-query/
        ├── SKILL.md                                 # [MODIFY] 恢复，移除多语种调用说明
        ├── references/api_reference.md              # [MODIFY] 恢复环境变量表与表名说明
        └── scripts/query_route.py                   # [MODIFY] 恢复，移除 HTML 卡片与 stdout 四语化、--find 别名、i18n 引导
```