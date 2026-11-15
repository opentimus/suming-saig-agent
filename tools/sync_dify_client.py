#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""把 tools/dify_client.py 同步到 4 个 Dify 技能各自的 scripts/ 目录。

技能是按目录独立安装的，运行期不能跨技能 import，所以公共客户端只能以副本形式
放进每个技能的 scripts/。本脚本保证「唯一来源 + 副本」不漂移：

    python3 tools/sync_dify_client.py --check   # 只校验，有漂移则退出码 1
    python3 tools/sync_dify_client.py --write   # 覆盖全部副本

改 dify_client.py 之后必须跑一次 --write，并在提交前一并提交副本。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "dify_client.py"
TARGETS = (
    ROOT / "skills" / "saig-intro" / "scripts" / "dify_client.py",
    ROOT / "skills" / "shuming-spu-intro" / "scripts" / "dify_client.py",
    ROOT / "skills" / "wuhan-intro" / "scripts" / "dify_client.py",
    ROOT / "skills" / "wuhan-scenic-intro" / "scripts" / "dify_client.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 Dify 公共客户端副本")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="校验副本与来源是否一致")
    group.add_argument("--write", action="store_true", help="用来源覆盖全部副本")
    args = parser.parse_args()

    if not SOURCE.is_file():
        print(f"错误：来源文件缺失 {SOURCE}", file=sys.stderr)
        return 2
    source_bytes = SOURCE.read_bytes()

    stale, missing = [], []
    for target in TARGETS:
        if not target.is_file():
            missing.append(target)
        elif target.read_bytes() != source_bytes:
            stale.append(target)

    if args.write:
        for target in TARGETS:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_bytes)
        print(f"已同步 {len(TARGETS)} 个副本 ← {SOURCE.relative_to(ROOT)}")
        return 0

    if missing or stale:
        for path in missing:
            print(f"缺失：{path.relative_to(ROOT)}", file=sys.stderr)
        for path in stale:
            print(f"漂移：{path.relative_to(ROOT)}", file=sys.stderr)
        print("副本与 tools/dify_client.py 不一致，请运行 --write", file=sys.stderr)
        return 1

    print(f"校验通过：{len(TARGETS)} 个副本与 tools/dify_client.py 一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
