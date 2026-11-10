/Users/wanbarry/saig-agent/wuhan-1day.html
# Jing Xiaowu

来自武汉的数命SPU城市AI接待员

## 类型

Agent 型（单个 AI 专家）

## 功能

- 介绍武汉城市历史与文化（自然地理、建置沿革、地方人文、社会经济）
- 武汉景区与旅游咨询（景点详情、玩法、季节主题、对比取舍、讲解词）
- 武汉旅游规划（G1-G9 固定线路查询与结构化行程单）
- 介绍数命SPU社区
- 介绍数命SPU与SAIG国际AI大赛

> 点到点导航、实时路况、驾车/公交具体走法不在本专家能力范围内。

## 使用示例

- 介绍一下数命SPU社区
- 介绍一下武汉磨山景区
- 武汉玩一天怎么玩

## 头像

头像已自动生成在 `avatars/` 目录下。如需替换为自定义头像，要求：

- 格式：PNG（推荐）或 JPG
- 尺寸：512×512 px
- 大小：单张不超过 500KB

## 安装

将专家包目录放到专家目录下：

```
/Users/wanbarry/.workbuddy/plugins/marketplaces/my-experts/plugins/jing-xiaowu/
```

然后运行注册命令使其可见：

```bash
python3 scripts/register_expert.py <expert-dir>
```

## 打包分享

```bash
zip -r jing-xiaowu.zip jing-xiaowu/
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
