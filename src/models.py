"""核心数据模型。

合规红线：Notice 强制保留 source_url / fetched_at / raw_snapshot，
保证每条公告可溯源、有抓取时间、有原文快照。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Notice:
    """一条公开招标/采购公告（抓取字段）。"""
    notice_id: str                      # 源站公告 ID（用于去重主键之一）
    title: str                          # 标题
    purchaser: str                      # 采购人
    region: str                         # 地区
    budget_amount: float | None         # 预算金额（元）
    registration_deadline: date | None # 报名截止
    bid_open_time: datetime | None     # 开标时间
    qualification: str                  # 资质要求（原文）
    source_url: str                     # 原文链接
    publish_time: date                  # 发布时间
    source: str = "mock"                # 数据源标识
    fetched_at: datetime = field(default_factory=_now)   # 抓取时间
    raw_snapshot: dict[str, Any] = field(default_factory=dict)  # 原文快照

    @property
    def content_fingerprint(self) -> str:
        """用于判定公告内容是否更新（与身份无关的字段集合）。"""
        import hashlib
        import json
        payload = {
            "title": self.title,
            "budget": self.budget_amount,
            "registration_deadline": self.registration_deadline.isoformat() if self.registration_deadline else None,
            "bid_open_time": self.bid_open_time.isoformat() if self.bid_open_time else None,
            "qualification": self.qualification,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class DimensionScore:
    """单维度得分。"""
    name: str
    score: float
    max_score: float
    reason: str
    risk: str = ""


@dataclass
class MatchResult:
    """匹配打分结果。"""
    notice: Notice
    score: int
    dimensions: list[DimensionScore]
    reasons: list[str]
    risks: list[str]
    recommended: bool
    summary: str = ""           # 3 行摘要（LLM 或模板）
    change_type: str = "new"    # 新增 / 更新
