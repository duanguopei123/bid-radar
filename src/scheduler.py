"""定时调度：每天 08:30（可配置），失败重试 + 日志。

使用 APScheduler 的 BackgroundScheduler；若未安装则给出明确安装提示。
时区由 config.yaml app.timezone 指定。
"""
from __future__ import annotations

import time
from typing import Callable

from .config import load_dotenv


def _run_with_retry(runner: Callable[[], object], max_attempts: int, backoff: int, db=None) -> None:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            runner()
            return
        except Exception as exc:  # noqa: BLE001 - 记录后重试
            last_exc = exc
            if db:
                db.audit("schedule", f"第 {attempt}/{max_attempts} 次运行失败：{exc}", level="WARN")
            else:
                print(f"[WARN] 第 {attempt}/{max_attempts} 次运行失败：{exc}")
            if attempt < max_attempts:
                time.sleep(backoff * attempt)
    if last_exc is not None:
        raise last_exc


def start_scheduler(cfg: dict, runner: Callable[[], object]) -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise SystemExit("定时调度需要 APScheduler，请先 pip install -r requirements.txt") from exc

    load_dotenv()
    sch = cfg["schedule"]
    tz = cfg["app"].get("timezone", "Asia/Shanghai")
    trigger = CronTrigger(hour=int(sch["cron_hour"]), minute=int(sch["cron_minute"]), timezone=tz)
    retry = sch.get("retry", {})

    def job() -> None:
        _run_with_retry(runner, int(retry.get("max_attempts", 3)),
                        int(retry.get("backoff_seconds", 5)))

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(job, trigger, id="daily_brief", name="每日招投标简报")
    print(f"定时任务已启动：每天 {sch['cron_hour']:02d}:{sch['cron_minute']:02d} ({tz})，Ctrl+C 退出")
    scheduler.start()
