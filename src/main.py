"""系统入口与组件装配。

用法：
    python -m src.main run-once     # 立即跑通全流程，生成本地简报
    python -m src.main schedule     # 按 config.yaml 每天 08:30 定时运行
"""
from __future__ import annotations

import argparse
import json
import sys

from .adapters.base import DataSourceAdapter
from .adapters.mock_adapter import MockAdapter
from .config import load_config
from .notifier.wecom_notifier import WecomWebhookNotifier
from .pipeline import Pipeline
from .storage.db import Database


def build_adapter(cfg: dict) -> DataSourceAdapter:
    """根据配置选择适配器。新增真实源时在此注册即可，主流程无需改动。"""
    active = cfg.get("active_adapter", "mock")
    for ds in cfg.get("datasources", []):
        if ds.get("name") == active and ds.get("enabled", False):
            if ds.get("type") == "mock":
                return MockAdapter(ds)
            # 真实源适配器在后续阶段实现并在上方注册；未启用时不应到达此处。
    # 兜底使用 mock，保证系统永远可运行（只读、离线）
    return MockAdapter({})


def build_pipeline(cfg: dict) -> Pipeline:
    db = Database(cfg["app"]["db_path"])
    adapter = build_adapter(cfg)
    ncfg = cfg.get("notifier", {})
    notifier = WecomWebhookNotifier(ncfg.get("webhook_url", ""), db=db)
    return Pipeline(cfg, adapter, db, notifier)


def cmd_run_once(cfg: dict) -> dict:
    pipeline = build_pipeline(cfg)
    try:
        result = pipeline.run()
    finally:
        pipeline.db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_schedule(cfg: dict) -> None:
    from .scheduler import start_scheduler
    start_scheduler(cfg, runner=lambda: cmd_run_once(cfg))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="招投标机会监测工作台（只读 MVP）")
    parser.add_argument("command", choices=["run-once", "schedule"],
                        help="run-once=立即跑一次；schedule=定时运行")
    parser.add_argument("--config", help="指定 config.yaml 路径")
    args = parser.parse_args(argv)

    cfg = load_config()
    if args.command == "run-once":
        cmd_run_once(cfg)
    else:
        cmd_schedule(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
