"""简报时间展示测试：不允许把 +00:00 这类原始偏移暴露给读者。

背景：开标时间、抓取时间在简报里曾直接 str(datetime) / isoformat()，
显示成「2026-11-23 09:00:00+00:00」，用户看到会以为系统搞错了时间。
"""
from datetime import date, datetime, timezone

from src.brief import fmt_dt, render_html, render_markdown
from src.models import MatchResult, Notice


def make_result(bid_open_time, fetched_at=None) -> MatchResult:
    notice = Notice(
        notice_id="TZ-1",
        title="徐州大件设备运输服务采购公告",
        purchaser="某单位",
        region="徐州",
        budget_amount=500000.0,
        registration_deadline=date.fromordinal(date.today().toordinal() + 5),
        bid_open_time=bid_open_time,
        qualification="道路运输经营许可证",
        source_url="https://example.org/tz/1",
        publish_time=date.today(),
        source="test",
        fetched_at=fetched_at or datetime(2026, 11, 19, 1, 20, 0, tzinfo=timezone.utc),
    )
    return MatchResult(
        notice=notice, score=88, recommended=True,
        dimensions=[], reasons=["地区匹配"], risks=[],
        summary="摘要", change_type="new",
    )


def test_fmt_dt_converts_utc_to_beijing():
    utc_dt = datetime(2026, 11, 23, 1, 0, 0, tzinfo=timezone.utc)
    assert fmt_dt(utc_dt) == "2026-11-23 09:00"


def test_fmt_dt_keeps_naive_datetime_as_local():
    naive = datetime(2026, 11, 23, 9, 0, 0)
    assert fmt_dt(naive) == "2026-11-23 09:00"


def test_fmt_dt_none_is_undisclosed_not_empty():
    assert fmt_dt(None) == "未披露"


def test_markdown_has_no_raw_utc_offset():
    md = render_markdown([make_result(datetime(2026, 11, 23, 1, 0, tzinfo=timezone.utc))],
                         run_date=date.today().isoformat(), owner_email="a@b.c")
    assert "+00:00" not in md
    assert "2026-11-23 09:00" in md


def test_html_has_no_raw_utc_offset():
    html = render_html([make_result(datetime(2026, 11, 23, 1, 0, tzinfo=timezone.utc))],
                       run_date=date.today().isoformat(), owner_email="a@b.c")
    assert "+00:00" not in html
    assert "2026-11-23 09:00" in html


def test_fetched_at_also_rendered_in_local_time():
    html = render_html([make_result(None)], run_date=date.today().isoformat(),
                       owner_email="a@b.c")
    # fetched_at 为 UTC 01:20，应显示为北京时间 09:20
    assert "2026-11-19 09:20" in html
    assert "T01:20" not in html


def test_custom_timezone_is_respected():
    utc_dt = datetime(2026, 11, 23, 1, 0, 0, tzinfo=timezone.utc)
    assert fmt_dt(utc_dt, "UTC") == "2026-11-23 01:00"
