#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 武汉海辞科技有限公司
"""把仓库打成可直接上传 WorkBuddy 的专家包（zip）。

WorkBuddy 的专家包就是「插件目录」本身：zip 根目录下必须有
`.codebuddy-plugin/plugin.json`，它与 `agents/`、`skills/`、`avatars/` 平级，
安装后落到 `plugins/marketplaces/<marketplace>/plugins/<name>/`。

    python3 tools/pack_expert.py                 # 产出 dist/jing-xiao-wu-<version>.zip
    python3 tools/pack_expert.py --out /tmp/x.zip
    python3 tools/pack_expert.py --list          # 只打印将被打包的文件

打包前会自动跑三项一致性校验（Dify 副本、线路文档、模板默认块），任一漂移即中止，
避免把过期数据发出去。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".codebuddy-plugin" / "plugin.json"
DIST = ROOT / "dist"

# 运行时必需 + 分发时需要的内容；tools/ 一并带上，让文档里对生成脚本的引用仍然成立
INCLUDE = (
    ".codebuddy-plugin",
    "agents",
    "skills",
    "avatars",
    "tools",
    "README.md",
    "LICENSE",
    "NOTICE",
    ".gitattributes",
)

# 任何位置出现都不要的垃圾
EXCLUDE_DIRS = {"__MACOSX", "__pycache__", ".git", ".codebuddy", ".vscode", "dist", ".venv"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
EXCLUDE_NAMES = {".DS_Store", ".env", ".gitignore"}

CHECKS = (
    ("Dify 副本", ["tools/sync_dify_client.py", "--check"]),
    ("线路文档", ["tools/gen_route_docs.py", "--check"]),
    ("模板默认块", ["tools/sync_template_defaults.py", "--check"]),
)


def fail(message: str, code: int = 2) -> int:
    print(f"错误：{message}", file=sys.stderr)
    return code


def load_manifest() -> dict:
    if not MANIFEST.is_file():
        raise SystemExit(f"清单缺失：{MANIFEST.relative_to(ROOT)}")
    with open(MANIFEST, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    for key in ("name", "version", "agents", "skills", "agentName", "avatar"):
        if not manifest.get(key):
            raise SystemExit(f"plugin.json 缺少字段：{key}")
    if manifest["name"] != manifest["agentName"]:
        raise SystemExit(
            f"plugin.json 的 name({manifest['name']}) 与 agentName({manifest['agentName']}) 不一致，"
            "上传后会出现两个条目"
        )
    return manifest


def verify_refs(manifest: dict) -> None:
    """清单里声明的 agent / skill / 头像必须在包内真实存在，否则装上就是坏包。"""
    missing = []
    for rel in list(manifest["agents"]) + list(manifest["skills"]) + [manifest["avatar"]]:
        target = ROOT / rel.lstrip("./")
        if not target.exists():
            missing.append(rel)
    for rel in manifest["skills"]:
        if not (ROOT / rel.lstrip("./") / "SKILL.md").is_file():
            missing.append(rel + "/SKILL.md")
    if missing:
        raise SystemExit("清单引用的文件不存在：" + "、".join(missing))


def collect() -> list:
    files = []
    for entry in INCLUDE:
        path = ROOT / entry
        if not path.exists():
            raise SystemExit(f"打包清单里的路径不存在：{entry}")
        if path.is_file():
            files.append(path)
            continue
        for child in sorted(path.rglob("*")):
            rel = child.relative_to(ROOT)
            if not child.is_file():
                continue
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            if child.suffix in EXCLUDE_SUFFIXES or child.name in EXCLUDE_NAMES:
                continue
            files.append(child)
    return files


def run_checks() -> None:
    for label, cmd in CHECKS:
        result = subprocess.run([sys.executable] + cmd, cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.returncode != 0:
            raise SystemExit(f"前置校验未通过（{label}）：\n{result.stdout.strip()}")
        print(f"  ✓ {label}", file=sys.stderr)


def build(out: Path, files: list, manifest: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            # zip 内路径相对仓库根，不套一层目录：WorkBuddy 认根目录的 .codebuddy-plugin/
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(f"已生成 {out}（{manifest['name']} {manifest['version']}，"
          f"{len(files)} 个文件，{out.stat().st_size / 1024 / 1024:.2f} MB）")


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 WorkBuddy 专家包")
    parser.add_argument("--out", default="", help="输出 zip 路径，默认 dist/<name>-<version>.zip")
    parser.add_argument("--list", action="store_true", help="只列出将打包的文件")
    parser.add_argument("--skip-checks", action="store_true", help="跳过前置一致性校验")
    args = parser.parse_args()

    manifest = load_manifest()
    verify_refs(manifest)
    files = collect()

    if args.list:
        for path in files:
            print(path.relative_to(ROOT).as_posix())
        print(f"--- 共 {len(files)} 个文件", file=sys.stderr)
        return 0

    if not args.skip_checks:
        run_checks()

    if args.out:
        out = Path(args.out).expanduser().resolve()
    else:
        safe = re.sub(r"[^A-Za-z0-9._-]", "-", manifest["name"])
        out = DIST / f"{safe}-{manifest['version']}.zip"
    build(out, files, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
