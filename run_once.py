#!/usr/bin/env python3
"""run-once：一条命令立即跑通全流程并在 out/ 输出简报文件。

    pip install -r requirements.txt
    cp .env.example .env
    python run_once.py
"""
import sys

from src.config import load_config
from src.main import cmd_run_once

if __name__ == "__main__":
    cfg = load_config()
    result = cmd_run_once(cfg)
    print("\n简报文件：")
    print(" -", result["markdown"])
    print(" -", result["html"])
    sys.exit(0)
