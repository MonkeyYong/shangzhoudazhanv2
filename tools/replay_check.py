#!/usr/bin/env python3
"""棋谱文件校验 CLI 工具。

用法：
    python tools/replay_check.py <path/to/replay.json> [<replay2.json> ...]

行为：
- 解析每个 JSON 文件为 Record
- 运行 validate() 检查所有错误
- 通过：打印走法符号 + 终局步数
- 失败：打印每条错误 + 退出码 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许从项目根目录运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codes.replay import Record


def main() -> int:
    parser = argparse.ArgumentParser(description="校验商周大战棋谱 JSON 文件")
    parser.add_argument("paths", nargs="+", help="棋谱 JSON 路径（一个或多个）")
    parser.add_argument("--quiet", "-q", action="store_true", help="只输出错误")
    args = parser.parse_args()

    exit_code = 0
    for path_str in args.paths:
        path = Path(path_str)
        if not path.exists():
            print(f"[ERROR] {path}: 文件不存在")
            exit_code = 1
            continue

        try:
            record = Record.load_json(str(path))
        except Exception as e:
            print(f"[ERROR] {path}: 解析失败: {e}")
            exit_code = 1
            continue

        errors = record.validate()
        if errors:
            print(f"[INVALID] {path}")
            for err in errors:
                print(f"   - {err}")
            exit_code = 1
            continue

        if not args.quiet:
            print(f"[OK] {path}  ({len(record.moves)} 步)")
            print(f"     preset={record.preset!r}  label={record.label!r}")
            for i, m in enumerate(record.moves, 1):
                notation = f"{m['from']}→{m['to']}"
                if m.get("capture"):
                    notation += "x"
                if m.get("clone"):
                    notation += "★"
                print(f"     {i:3}. {notation}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
