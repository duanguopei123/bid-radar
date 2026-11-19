"""腾讯云函数（SCF）入口：定时触发时执行一次完整流程。

部署要点（详见 README 第六节）：
- 函数入口填 `index.main_handler`
- 依赖：requirements.txt（PyYAML / requests / Jinja2 / APScheduler 中云函数只需前三个）
- 环境变量：LLM_*、WECOM_WEBHOOK_URL（在控制台配置，不要打进代码包）
- 文件系统：SCF 的 /opt 与代码目录只读，需把 out/data 指向 /tmp（见 configure_for_scf）
"""
from __future__ import annotations

import os
from pathlib import Path

from src.config import load_config
from src.main import cmd_run_once


def configure_for_scf(cfg: dict) -> dict:
    """把可写目录改到 /tmp，避免云函数只读文件系统报错。"""
    app = cfg.setdefault("app", {})
    tmp = Path("/tmp")
    app["db_path"] = str(tmp / "bidding.db")
    app["data_dir"] = str(tmp)
    app["out_dir"] = str(tmp / "out")
    app["log_dir"] = str(tmp / "logs")
    Path(app["out_dir"]).mkdir(parents=True, exist_ok=True)
    return cfg


def main_handler(event, context):
    cfg = load_config()
    if os.environ.get("SCF_FUNCTIONNAME") or os.environ.get("TENCENTCLOUD_RUNENV"):
        cfg = configure_for_scf(cfg)
    result = cmd_run_once(cfg)
    return {"code": 0, "msg": "ok", "result": result}
