"""系统入口与组件装配。

用法：
    python -m src.main run-once     # 立即跑通全流程，生成本地简报
    python -m src.main schedule     # 按 config.yaml 每天 08:30 定时运行
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters.base import DataSourceAdapter
from .adapters.mock_adapter import MockAdapter
from .config import load_config
from .notifier.factory import build_notifier
from .pipeline import Pipeline
from .storage.db import Database


def build_adapter(cfg: dict) -> DataSourceAdapter:
    """根据配置选择适配器。新增真实源时在此注册即可，主流程无需改动。"""
    active = cfg.get("active_adapter", "mock")
    for ds in cfg.get("datasources", []):
        if ds.get("name") == active:
            if not ds.get("enabled", False):
                raise ValueError(f"数据源 {active} 未启用")
            if ds.get("type") == "mock":
                return MockAdapter(ds)
            raise ValueError(f"数据源 {active} 的类型 {ds.get('type')!r} 尚未注册")
    raise ValueError(f"找不到数据源 {active}")


def build_pipeline(cfg: dict) -> Pipeline:
    db = Database(cfg["app"]["db_path"])
    adapter = build_adapter(cfg)
    notifier = build_notifier(cfg, db=db)
    return Pipeline(cfg, adapter, db, notifier)


def cmd_run_once(cfg: dict, include_unchanged: bool = False) -> dict:
    pipeline = build_pipeline(cfg)
    try:
        result = pipeline.run(include_unchanged=include_unchanged)
    finally:
        pipeline.db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def _result_failed(result: dict) -> bool:
    return (
        result.get("status") == "failed"
        or result.get("delivery_status") == "failed"
        or int(result.get("failed") or 0) > 0
    )


def cmd_schedule(cfg: dict) -> None:
    from .scheduler import start_scheduler

    def scheduled_run() -> dict:
        result = cmd_run_once(cfg)
        if _result_failed(result):
            raise RuntimeError("定时任务处理或投递失败")
        return result

    start_scheduler(cfg, runner=scheduled_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="招投标机会监测工作台（只读 MVP）")
    parser.add_argument("command", choices=["run-once", "schedule"],
                        help="run-once=立即跑一次；schedule=定时运行")
    parser.add_argument("--config", help="指定 config.yaml 路径")
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config)) if args.config else load_config()
    if args.command == "run-once":
        result = cmd_run_once(cfg)
    else:
        cmd_schedule(cfg)
        return 0
    return 1 if _result_failed(result) else 0


if __name__ == "__main__":
    sys.exit(main())
