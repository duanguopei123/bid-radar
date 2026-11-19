"""Mock 适配器集成测试：fetch -> 去重/入库 -> 打分 -> 简报 全链路（本地，无网络）。"""
import tempfile

from src.adapters.mock_adapter import MockAdapter
from src.brief import render_html, render_markdown
from src.matcher.scorer import score_notice
from src.storage.db import Database
from tests.conftest import CFG


def test_mock_adapter_returns_complete_notices():
    notices = MockAdapter().fetch()
    assert len(notices) >= 5
    required = ["notice_id", "title", "purchaser", "region", "budget_amount",
                "registration_deadline", "bid_open_time", "qualification",
                "source_url", "publish_time"]
    for n in notices:
        assert all(hasattr(n, f) for f in required)
        assert n.source_url.startswith("https://")
        assert n.fetched_at is not None
        assert isinstance(n.raw_snapshot, dict) and n.raw_snapshot  # 原文快照


def test_full_pipeline_offline(tmp_path=None):
    with tempfile.TemporaryDirectory() as d:
        db = Database(f"{d}/test.db")
        notices = MockAdapter().fetch()

        first_changes = [db.upsert_notice(n)[1] for n in notices]
        assert all(c == "new" for c in first_changes)

        # 第二次抓取：同一公告不重复入库（去重/增量）
        second_changes = [db.upsert_notice(n)[1] for n in notices]
        assert all(c == "unchanged" for c in second_changes)

        results = [score_notice(n, CFG) for n in notices]
        assert any(r.recommended for r in results)
        assert any(not r.recommended for r in results)  # 非行业项目应被过滤

        for n, r in zip(notices, results):
            r.summary = "\n".join([
                f"项目：{n.title}",
                f"匹配：{r.score} 分",
                "提示：人工确认",
            ])
            db.save_match(db.identity_hash(n) and db.get_notice(db.identity_hash(n))["id"], r)

        md = render_markdown(results, "2026-01-01", "a@b.com")
        html = render_html(results, "2026-01-01", "a@b.com")
        assert "招投标机会日报" in md and "原文链接" in md
        assert "<html" in html and "查看原文公告" in html
        assert any(r.change_type == "new" for r in results)
        db.close()
