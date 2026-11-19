"""运行时正确性、静默失败与增量投递状态的回归测试。

这些用例描述目标行为，当前生产代码尚未实现，因此第一批应先全部失败。
"""
from __future__ import annotations

import copy
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

import index
import run_once
from src import main as main_module
from src.adapters.base import DataSourceAdapter
from src.brief import days_countdown, render_markdown
from src.main import build_adapter
from src.matcher.scorer import score_notice
from src.models import Notice
from src.pipeline import Pipeline
from src.scheduler import _run_with_retry
from src.storage.db import Database
from tests.conftest import CFG


ROOT = Path(__file__).resolve().parent.parent
BUSINESS_DATE = date(2026, 11, 20)


def _cfg(tmp_path: Path) -> dict:
    cfg = copy.deepcopy(CFG)
    cfg["app"] = dict(
        cfg["app"],
        db_path=str(tmp_path / "bidding.db"),
        out_dir=str(tmp_path / "out"),
    )
    cfg["llm"] = dict(cfg.get("llm", {}), enabled=False)
    cfg["notifier"] = dict(cfg.get("notifier", {}), enabled=False)
    return cfg


def _notice(
    notice_id: str,
    *,
    title: str = "徐州市普货运输服务采购公告",
    deadline: date | None = None,
) -> Notice:
    return Notice(
        notice_id=notice_id,
        title=title,
        purchaser="徐州某单位",
        region="江苏徐州",
        budget_amount=300_000.0,
        registration_deadline=deadline or (BUSINESS_DATE + timedelta(days=5)),
        bid_open_time=None,
        qualification="投标人须具有道路运输经营许可证",
        source_url=f"https://example.org/{notice_id}",
        publish_time=BUSINESS_DATE,
        source="test",
    )


class _StaticAdapter(DataSourceAdapter):
    name = "test"

    def __init__(self, notices: list[Notice]):
        super().__init__({})
        self.notices = notices

    def fetch(self) -> list[Notice]:
        return self.notices


class _FlakyNotifier:
    def __init__(self):
        self.calls = 0

    def send(self, subject: str, body: str) -> bool:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("webhook 502")
        return True


def test_failed_scoring_is_retried_on_next_run(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    db = Database(cfg["app"]["db_path"])
    pipeline = Pipeline(cfg, _StaticAdapter([_notice("retry-1")]), db)
    real_score = score_notice
    calls = {"count": 0}

    def flaky_score(notice, scoring_cfg, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("scoring failed")
        return real_score(notice, scoring_cfg, **kwargs)

    monkeypatch.setattr("src.pipeline.score_notice", flaky_score)

    first = pipeline.run()
    assert first["failed"] == 1

    second = pipeline.run()
    assert second["failed"] == 0
    assert second["new_or_updated"] == 1
    db.close()


def test_failed_push_stays_pending_and_is_retried(tmp_path):
    cfg = _cfg(tmp_path)
    cfg["notifier"]["enabled"] = True
    db = Database(cfg["app"]["db_path"])
    notifier = _FlakyNotifier()
    pipeline = Pipeline(
        cfg,
        _StaticAdapter([_notice("push-retry-1")]),
        db,
        notifier=notifier,
    )

    first = pipeline.run()
    assert first["delivery_status"] == "failed"
    assert first["pushed"] is False

    second = pipeline.run()
    assert second["delivery_status"] == "sent"
    assert notifier.calls == 2
    db.close()


def test_expired_blocks_recommendation_without_changing_score(tmp_path):
    cfg = _cfg(tmp_path)
    expired = _notice(
        "expired-1",
        deadline=BUSINESS_DATE - timedelta(days=1),
    )

    result = score_notice(expired, cfg, business_date=BUSINESS_DATE)

    assert result.score > int(cfg["matching"]["recommend_threshold"])
    assert result.recommended is False
    assert next(d for d in result.dimensions if d.name == "deadline").score == 0.0

    unknown = _notice("unknown-deadline-1", deadline=None)
    unknown_result = score_notice(unknown, cfg, business_date=BUSINESS_DATE)
    assert unknown_result.recommended is True
    assert not any("已过报名截止" in risk for risk in unknown_result.risks)


def test_unknown_active_adapter_fails_instead_of_using_mock(tmp_path):
    cfg = _cfg(tmp_path)
    cfg["active_adapter"] = "misspelled-source"

    with pytest.raises(ValueError, match="misspelled-source"):
        build_adapter(cfg)


def test_scf_requires_explicit_persistent_database(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.delenv("BID_RADAR_DB_PATH", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        index.configure_for_scf(cfg)

    message = str(exc_info.value)
    assert "持久化数据库" in message
    assert "BID_RADAR_DB_PATH" in message


def test_custom_config_argument_is_honored(tmp_path, monkeypatch):
    seen: dict[str, object] = {}

    def fake_load_config(path=None):
        seen["path"] = path
        return _cfg(tmp_path)

    def fake_run_once(cfg, include_unchanged=False):
        return {"status": "ok", "pushed": False}

    monkeypatch.setattr(main_module, "load_config", fake_load_config)
    monkeypatch.setattr(main_module, "cmd_run_once", fake_run_once)
    custom_path = tmp_path / "customer-config.yaml"

    assert main_module.main(["run-once", "--config", str(custom_path)]) == 0
    assert Path(seen["path"]) == custom_path


def test_business_date_is_shared_by_scoring_and_brief():
    deadline = date(2026, 11, 21)

    assert days_countdown(deadline, business_date=BUSINESS_DATE) == "剩余 1 天"

    notice = _notice("time-1", deadline=deadline)
    result = score_notice(notice, copy.deepcopy(CFG), business_date=BUSINESS_DATE)
    result.summary = "项目概况\n匹配亮点\n风险提醒"
    markdown = render_markdown(
        [result],
        run_date=BUSINESS_DATE.isoformat(),
        owner_email="owner@example.org",
        business_date=BUSINESS_DATE,
    )
    assert "剩余 1 天" in markdown


def test_one_bad_notice_does_not_drop_later_notices(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    db = Database(cfg["app"]["db_path"])
    bad = _notice("bad-1", title="BAD 评分异常项目")
    good = _notice("good-1", title="GOOD 正常推荐项目")
    pipeline = Pipeline(cfg, _StaticAdapter([bad, good]), db)
    real_score = score_notice

    def selective_score(notice, scoring_cfg, **kwargs):
        if notice.title.startswith("BAD"):
            raise ValueError("malformed notice")
        return real_score(notice, scoring_cfg, **kwargs)

    monkeypatch.setattr("src.pipeline.score_notice", selective_score)

    result = pipeline.run()

    assert result["failed"] == 1
    assert result["new_or_updated"] == 1
    assert "GOOD 正常推荐项目" in Path(result["markdown"]).read_text(encoding="utf-8")
    db.close()


def test_scheduler_reraises_after_retry_exhaustion():
    def always_fails():
        raise RuntimeError("pipeline still down")

    with pytest.raises(RuntimeError, match="pipeline still down"):
        _run_with_retry(always_fails, max_attempts=2, backoff=0)


def test_entrypoints_report_failed_delivery(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    failed_result = {
        "status": "failed",
        "delivery_status": "failed",
        "pushed": False,
        "recommended": 1,
    }

    monkeypatch.setattr(index, "load_config", lambda: cfg)
    monkeypatch.setattr(index, "cmd_run_once", lambda loaded_cfg: failed_result)
    response = index.main_handler({}, None)
    assert response["code"] != 0
    assert "失败" in response["msg"]

    monkeypatch.setattr(run_once, "load_config", lambda: cfg)
    monkeypatch.setattr(run_once, "cmd_run_once", lambda loaded_cfg, **kwargs: failed_result)
    assert run_once.main([]) != 0


def test_launcher_uses_only_venv_and_stops_before_opening_stale_brief():
    script = (ROOT / "启动工作台.bat").read_text(encoding="utf-8")

    assert r".venv\Scripts\python.exe" in script
    assert "AppData" not in script
    assert not re.search(r'set\s+"PY=python"', script, flags=re.IGNORECASE)

    error_index = script.lower().find("if errorlevel 1")
    open_index = script.lower().find("opening latest brief")
    assert error_index >= 0
    assert open_index > error_index
    failure_branch = script[error_index:open_index].lower()
    assert "goto" in failure_branch or "exit /b" in failure_branch
    assert "pause" in script.lower()
