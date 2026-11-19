"""匹配打分逻辑单元测试（验收要求：全部通过）。"""
from datetime import date

import pytest

from src.matcher.rules import (budget_score, deadline_score, industry_score,
                               qualification_score, region_score)
from src.matcher.scorer import score_notice
from src.models import Notice
from tests.conftest import CFG


def make_notice(**overrides) -> Notice:
    defaults = dict(
        notice_id="T-1", title="徐州普货运输服务采购", purchaser="某单位",
        region="徐州", budget_amount=300000.0,
        registration_deadline=date.fromordinal(date.today().toordinal() + 5),
        bid_open_time=None, qualification="道路运输经营许可证",
        source_url="https://example.org/t/1", publish_time=date.today(),
        source="test",
    )
    defaults.update(overrides)
    return Notice(**defaults)


def test_region_full_and_mismatch():
    ratio, reason, risk = region_score("江苏徐州", ["徐州", "江苏省"])
    assert ratio == 1.0 and "徐州" in reason and risk == ""
    ratio, reason, risk = region_score("广东深圳", ["徐州", "江苏省"])
    assert ratio == 0.0 and "不匹配" in reason and risk != ""


def test_industry_hit_and_miss():
    ratio, reason, _ = industry_score("大件运输与物流服务", ["运输", "物流"])
    assert ratio == 1.0 and "运输" in reason
    ratio, _, risk = industry_score("办公用品采购", ["运输", "物流"])
    assert ratio == 0.0 and risk != ""


def test_qualification_missing_risk():
    ratio, _, risk = qualification_score("道路运输经营许可证", [{"name": "道路运输经营许可证"}])
    assert ratio == 1.0
    ratio2, _, risk2 = qualification_score(
        "道路危险货物运输许可证", [{"name": "道路运输经营许可证"}])
    assert ratio2 <= 0.4 and "危险货物" in risk2


def test_budget_soft_filter_keeps_but_penalizes():
    cfg = {"min": 10000, "max": 1000000}
    ratio, _, risk = budget_score(500000.0, cfg)
    assert ratio == 1.0 and risk == ""
    ratio, reason, risk = budget_score(2500000.0, cfg)
    assert ratio < 1.0 and "超出" in reason and risk != ""  # 软性过滤：扣分但保留


def test_deadline_expired_and_urgent():
    ratio, _, risk = deadline_score(date.fromordinal(date.today().toordinal() - 1))
    assert ratio == 0.0 and "已过" in risk
    ratio, reason, _ = deadline_score(date.fromordinal(date.today().toordinal() + 2))
    assert ratio == 1.0 and "即将" in reason


def test_full_score_in_range():
    result = score_notice(make_notice(), CFG)
    assert 0 <= result.score <= 100
    assert result.score >= 90
    assert result.recommended is True
    assert all(d.reason for d in result.dimensions)


def test_bad_qualification_reduces_score_and_adds_risk():
    good = score_notice(make_notice(), CFG)
    bad = score_notice(make_notice(qualification="道路危险货物运输许可证"), CFG)
    assert bad.score < good.score
    assert any("资质缺项" in r for r in bad.risks)
