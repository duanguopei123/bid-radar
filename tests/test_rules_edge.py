"""回归测试：覆盖代码审查中发现并修复的边界问题。

每个用例对应一个已修复的真实缺陷，防止以后改回去。
"""
from datetime import date

from src.adapters.mock_adapter import MockAdapter
from src.matcher.rules import budget_score, qualification_score, region_score
from src.models import Notice
from src.pipeline import Pipeline
from src.storage.db import Database
from tests.conftest import CFG


def test_province_not_treated_as_city():
    """回归：「江苏省」三字省份名不能被当作城市名给满分。"""
    ratio, reason, risk = region_score("江苏省南京市", ["徐州", "江苏省"])
    assert ratio == 0.6
    assert "省份" in reason and risk


def test_city_wins_regardless_of_config_order():
    """城市命中优先于省份命中，与配置顺序无关。"""
    ratio, _, _ = region_score("江苏省徐州市", ["江苏省", "徐州"])
    assert ratio == 1.0


def test_zero_or_none_budget_means_undisclosed():
    """回归：预算 0 不能按「低于下限」处理，应视为未披露。"""
    ratio, reason, _ = budget_score(0, {"min": 10000, "max": 1000000})
    assert ratio == 0.4 and "未披露" in reason
    ratio, reason, _ = budget_score(None, {"min": 10000, "max": 1000000})
    assert ratio == 0.4 and "未披露" in reason


def test_qualification_core_word_match():
    """回归：公告表述与资质全名略有差异时也能命中（去掉硬编码特例）。"""
    ratio, reason, _ = qualification_score(
        "投标人须具备道路运输经营许可，并有普货运输经验",
        [{"name": "道路运输经营许可证"}],
    )
    assert ratio == 1.0 and "道路运输经营许可证" in reason


def test_identity_hash_fallback_avoids_collision():
    """回归：notice_id 与 source_url 同时为空时，不同公告不能撞同一个去重键。"""
    db = Database(":memory:")
    base = dict(notice_id="", region="徐州", budget_amount=1.0,
                registration_deadline=None, bid_open_time=None,
                qualification="", source_url="", publish_time=date.today(), source="t")
    a = Notice(title="项目甲", purchaser="甲单位", **base)
    b = Notice(title="项目乙", purchaser="乙单位", **base)
    assert db.identity_hash(a) != db.identity_hash(b)
    db.close()


class _BrokenNotifier:
    def send(self, subject, body):
        raise RuntimeError("webhook 502")


def test_notifier_failure_does_not_break_run(tmp_path):
    """回归：推送失败不能中断流程，简报仍应生成并返回结果。"""
    cfg = dict(CFG)
    cfg["app"] = dict(cfg["app"],
                      out_dir=str(tmp_path / "out"),
                      db_path=str(tmp_path / "t.db"))
    cfg["notifier"] = dict(cfg.get("notifier", {}), enabled=True)

    db = Database(cfg["app"]["db_path"])
    pipe = Pipeline(cfg, MockAdapter(), db, notifier=_BrokenNotifier())
    result = pipe.run()

    assert result["pushed"] is False
    assert result["html"] and result["markdown"]
    db.close()
