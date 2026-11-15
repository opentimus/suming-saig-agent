# Jing Xiaowu

来自武汉的数命SPU城市AI接待员

## 类型

Agent 型（单个 AI 专家）

## 功能

- 介绍武汉城市历史与文化（自然地理、建置沿革、地方人文、社会经济）
- 武汉景区与旅游咨询（景点详情、玩法、季节主题、对比取舍、讲解词）
- 武汉导览（单页双视图：离线交互地图，含可拖动平移的手绘底图 + 由 `spots.json` 驱动的「编号 + 名称」DOM 景点标签 + G1–G9 多选线路筛选 + 对应按片区清单；右上角「编辑景点」可拖动定位、点击空白新增、点选改名称／类型／简介／所属线路或删除，改动保存在本机浏览器并可导出／导入 JSON；底部行程区固定展开、不可折叠：全景导览时显示引导占位，在线路查询时按 G1–G9 每组一张卡片（标题带 G 代号）、组内紧凑单列列出景点，上方筛选与卡片一一联动，每组右上角「+」可加景点、每行「×」可删景点（仅当页生效，区内不重复放线路按钮）。两种模式共用同一个 `wuhan-guide.html`，同名覆盖、各自只执行一次脚本）
- 介绍数命SPU社区
- 介绍数命SPU与SAIG国际AI大赛

> 点到点导航、实时路况、驾车/公交具体走法不在本专家能力范围内。

## 使用示例

- 介绍一下数命SPU社区
- 介绍一下武汉磨山景区
- 武汉玩一天怎么玩
- 武汉全景导览

## 头像

头像已自动生成在 `avatars/` 目录下。如需替换为自定义头像，要求：

- 格式：PNG（推荐）或 JPG
- 尺寸：512×512 px
- 大小：单张不超过 500KB

## 目录结构

```
<repo>/                             # 仓库根目录（安装时整体作为插件目录）
├── .codebuddy-plugin/plugin.json   # 插件清单：声明 1 个 agent 与 5 个 skill
├── agents/jing-xiao-wu.md          # 唯一的 agent 定义（路由与回答档位）
├── skills/                         # 每个子目录是一个可独立安装的技能
│   ├── wuhan-guide/                # 武汉导览：离线地图 + 行程卡片
│   ├── wuhan-scenic-intro/         # 武汉景区咨询（含 G1-G9 线路概览）
│   ├── wuhan-intro/                # 武汉城市历史与地情
│   ├── shuming-spu-intro/          # 数命SPU 社区
│   └── saig-intro/                 # SAIG 国际AI大赛
├── tools/                          # 仓库级维护脚本（不随技能安装）
└── avatars/expert.png
```

## 安装

把这个仓库整体作为插件目录安装，目录名保持 `jing-xiao-wu`（与 `.codebuddy-plugin/plugin.json`
的 `name`、`agentName` 一致）。各宿主的插件根目录以自身文档为准，常见位置：

```bash
# CodeBuddy 插件目录
cp -R . "$HOME/.codebuddy/plugins/jing-xiao-wu"
# WorkBuddy marketplace 插件目录
cp -R . "$HOME/.workbuddy/plugins/marketplaces/my-experts/plugins/jing-xiao-wu"
```

`plugin.json` 里的 `agents` / `skills` 都是相对本目录的路径，宿主加载插件后按清单自动发现
agent 与技能，**不需要**额外的注册脚本。仓库内所有文档与脚本也统一使用相对于插件根的
`skills/<name>/...` 路径，不写死任何用户目录。

## 维护脚本

`tools/` 下的脚本处理跨技能的一致性，修改对应文件后各跑一次校验并在提交前同步：

```bash
# Dify 公共客户端：唯一实现 → 4 个技能副本
python3 tools/sync_dify_client.py --write    # 改完 tools/dify_client.py 后同步
python3 tools/sync_dify_client.py --check    # 校验副本是否漂移

# 线路参考文档：由接口数据生成，禁止手改
python3 tools/gen_route_docs.py --snapshot   # 联网拉「旅遊线路」表全量写入 tools/route_snapshot.json
python3 tools/gen_route_docs.py --write      # 用快照重生成 route_codes.md / route_overview.md
python3 tools/gen_route_docs.py --check      # 校验两份文档与快照一致

# 模板默认块：让「直接打开模板」与生成产物共用同一份 spots.json 快照
python3 tools/sync_template_defaults.py --write   # 改完 spots.json 后刷新模板默认块
python3 tools/sync_template_defaults.py --check   # 校验模板默认块是否漂移
```

改完数据后生成页面的常规顺序：改 `assets/spots.json` → `sync_template_defaults.py --write`
→ `show_map.py --out <工作区>/wuhan-guide.html`。

## 打包分享

```bash
# 在仓库父目录执行，产物含 .codebuddy-plugin/plugin.json
zip -r jing-xiao-wu.zip jing-xiao-wu/ -x "jing-xiao-wu/.git/*" -x "jing-xiao-wu/.DS_Store"
```

## 开源协议

本项目采用 **GNU General Public License v3.0** 开源协议（SPDX: `GPL-3.0-only`），
许可证全文见 [`LICENSE`](LICENSE)，版权与署名说明见 [`NOTICE`](NOTICE)。

- **版权所有 / 署名**：Copyright (C) 2026 武汉海辞科技有限公司
- 可自由使用、修改和分发；分发原作或衍生作品时须保留版权与许可证声明，
  以同一协议开源整个衍生作品并提供相应源代码。
- 按"现状"提供，不附带任何担保（详见 `LICENSE` 第 15、16 节）。

项目内 `agents/`、`skills/`、`avatars/` 及配置资源均适用上述协议；各源文件
头部亦标注了 `SPDX-License-Identifier: GPL-3.0-only`。
