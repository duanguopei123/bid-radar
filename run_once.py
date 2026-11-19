#!/usr/bin/env python3
"""run-once：一条命令立即跑通全流程并在 out/ 输出简报文件。

    pip install -r requirements.txt
    cp .env.example .env
    python run_once.py          # 只报今日新增/更新（每日增量简报）
    python run_once.py --all    # 展示当前全部可投项目（看板/复盘/演示）
"""
import sys

from src.config import load_config
from src.main import cmd_run_once

if __name__ == "__main__":
    include_all = "--all" in sys.argv[1:]
    cfg = load_config()
    result = cmd_run_once(cfg, include_unchanged=include_all)
    print("\n简报文件：")
    print(" -", result["markdown"])
    print(" -", result["html"])
    if result["recommended"] == 0:
        print("\n提示：本次无新增推荐项目。加 --all 可查看当前全部可投项目。")
    sys.exit(0)
