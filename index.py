"""腾讯云函数（SCF）入口：定时触发时执行一次完整流程。

部署要点（详见 README 第六节）：
- 函数入口填 `index.main_handler`
- 依赖：requirements.txt（PyYAML / requests / Jinja2 / APScheduler 中云函数只需前三个）
- 环境变量：LLM_*、WECOM_WEBHOOK_URL、BID_RADAR_DB_PATH（在控制台配置）
- 文件系统：SCF 的 /opt 与代码目录只读，需把 out/data 指向 /tmp（见 configure_for_scf）
- 持久化数据库：BID_RADAR_DB_PATH 必须指向可跨冷启动保留的 SQLite 文件
"""
from __future__ import annotations

import os
from pathlib import Path

from src.config import load_config
from src.main import cmd_run_once


def configure_for_scf(cfg: dict) -> dict:
    """云函数必须使用持久化数据库；仅把临时产出目录放到 /tmp。"""
    app = cfg.setdefault("app", {})
    db_path = os.environ.get("BID_RADAR_DB_PATH", "").strip()
    if not db_path:
        raise RuntimeError(
            "缺少持久化数据库配置 BID_RADAR_DB_PATH，拒绝使用临时数据库启动云函数"
        )
    tmp = Path("/tmp")
    app["db_path"] = db_path
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
    failed = (
        result.get("status") == "failed"
        or result.get("delivery_status") == "failed"
        or int(result.get("failed") or 0) > 0
    )
    if failed:
        return {"code": 1, "msg": "处理或投递失败，请检查 result", "result": result}
    return {"code": 0, "msg": "ok", "result": result}
