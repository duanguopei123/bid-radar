"""Mock 数据源适配器。

【合规红线】本适配器完全离线、无任何网络请求，更无对外写入/报名/提交行为。
用于在没有授权数据源时跑通全链路；字段结构与真实源适配器一致，方便平滑替换。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ..models import Notice
from .base import DataSourceAdapter

TODAY = date.today()


def _d(offset_days: int) -> date:
    return TODAY + timedelta(days=offset_days)


def _dt(offset_days: int, hour: int = 9) -> datetime:
    return datetime.combine(_d(offset_days), datetime.min.time().replace(hour=hour), tzinfo=timezone.utc)


class MockAdapter(DataSourceAdapter):
    """提供覆盖各类边界的样例公告：高分、异地、超预算、资质缺项、即将截止。"""
    name = "mock"

    def fetch(self) -> list[Notice]:
        raw_items = [
            {
                "notice_id": "MOCK-2026-0001",
                "title": "徐州市城市轨道交通大件设备运输服务采购公告",
                "purchaser": "徐州市轨道交通集团",
                "region": "江苏徐州",
                "budget_amount": 680000.0,
                "registration_deadline": _d(6),
                "bid_open_time": _dt(8),
                "qualification": "投标人须具有道路运输经营许可证，具备大件运输经验",
                "source_url": "https://example.org/mock/notice/0001",
                "publish_time": _d(-1),
            },
            {
                "notice_id": "MOCK-2026-0002",
                "title": "徐州某普货物流运输项目招标公告",
                "purchaser": "徐州某制造有限公司",
                "region": "徐州",
                "budget_amount": 320000.0,
                "registration_deadline": _d(2),
                "bid_open_time": _dt(4),
                "qualification": "道路运输经营许可证，普通货运资质",
                "source_url": "https://example.org/mock/notice/0002",
                "publish_time": _d(-2),
            },
            {
                "notice_id": "MOCK-2026-0003",
                "title": "南京市仓储物流服务采购（异地高预算）",
                "purchaser": "南京某供应链公司",
                "region": "江苏南京",
                "budget_amount": 2500000.0,
                "registration_deadline": _d(12),
                "bid_open_time": _dt(15),
                "qualification": "道路运输经营许可证",
                "source_url": "https://example.org/mock/notice/0003",
                "publish_time": _d(-3),
            },
            {
                "notice_id": "MOCK-2026-0004",
                "title": "徐州办公用品采购项目（非本行业）",
                "purchaser": "徐州市某事业单位",
                "region": "徐州",
                "budget_amount": 150000.0,
                "registration_deadline": _d(9),
                "bid_open_time": _dt(11),
                "qualification": "无特殊资质要求",
                "source_url": "https://example.org/mock/notice/0004",
                "publish_time": _d(-1),
            },
            {
                "notice_id": "MOCK-2026-0005",
                "title": "徐州大型设备运输项目（资质缺项+即将截止）",
                "purchaser": "徐州某重工企业",
                "region": "徐州",
                "budget_amount": 900000.0,
                "registration_deadline": _d(1),
                "bid_open_time": _dt(3),
                "qualification": "须具有道路危险货物运输许可证及大件运输四级资质",
                "source_url": "https://example.org/mock/notice/0005",
                "publish_time": _d(-4),
            },
            {
                "notice_id": "MOCK-2026-0006",
                "title": "徐州普货运输服务询价公告（低预算）",
                "purchaser": "徐州某商贸公司",
                "region": "徐州",
                "budget_amount": 6000.0,
                "registration_deadline": _d(5),
                "bid_open_time": _dt(7),
                "qualification": "道路运输经营许可证",
                "source_url": "https://example.org/mock/notice/0006",
                "publish_time": _d(-1),
            },
        ]
        notices: list[Notice] = []
        for item in raw_items:
            notices.append(
                Notice(
                    source=self.name,
                    raw_snapshot=dict(item),  # 原文快照
                    **item,
                )
            )
        return notices
