"""资质匹配打分：五维加权得到 0-100 分 + 匹配理由 + 风险提示。

纯函数实现，便于单元测试。不依赖 LLM、不做任何对外动作。
"""
from __future__ import annotations

import logging

from ..models import DimensionScore, MatchResult, Notice
from . import rules

logger = logging.getLogger(__name__)


def score_notice(notice: Notice, cfg: dict) -> MatchResult:
    company = cfg["company"]
    mcfg = cfg["matching"]
    weights = mcfg["weights"]

    total_weight = sum(float(v) for v in weights.values())
    if abs(total_weight - 100) > 1:
        logger.warning(
            "matching.weights 总和为 %.1f（应为 100），总分将按实际权重累加，请检查 config.yaml",
            total_weight,
        )

    dims: list[DimensionScore] = []

    def add(name: str, ratio: float, reason: str, risk: str) -> None:
        w = float(weights.get(name, 0))
        dims.append(DimensionScore(name=name, score=round(ratio * w, 2),
                                   max_score=w, reason=reason, risk=risk))

    r, reason, risk = rules.region_score(notice.region, company.get("regions", []))
    add("region", r, reason, risk)

    text = f"{notice.title} {notice.qualification}"
    r, reason, risk = rules.industry_score(text, company.get("industry_keywords", []))
    add("industry", r, reason, risk)

    r, reason, risk = rules.qualification_score(notice.qualification, company.get("qualifications", []))
    add("qualification", r, reason, risk)

    r, reason, risk = rules.budget_score(notice.budget_amount, company.get("budget", {}))
    add("budget", r, reason, risk)

    r, reason, risk = rules.deadline_score(notice.registration_deadline)
    add("deadline", r, reason, risk)

    total = round(sum(d.score for d in dims))
    total = max(0, min(100, total))
    reasons = [f"[{d.name}] {d.reason}" for d in dims if d.reason]
    risks = [d.risk for d in dims if d.risk]
    recommended = total >= int(mcfg.get("recommend_threshold", 55))

    return MatchResult(
        notice=notice,
        score=total,
        dimensions=dims,
        reasons=reasons,
        risks=risks,
        recommended=recommended,
    )
