"""评分规则与权重常量（纯配置，便于单测与调整）。"""
from __future__ import annotations


def region_score(notice_region: str, company_regions: list[str]) -> tuple[float, str, str]:
    """地区维度：命中具体城市满分，命中省份部分分，异地 0 分并提示风险。"""
    text = notice_region or ""
    for r in company_regions:
        if r in text:
            if len(r) <= 3:  # 城市级，如"徐州"
                return 1.0, f"地区命中：{r}", ""
            # 省级，如"江苏省"
            return 0.6, f"地区命中省份（非目标城市）：{r}", "本省但非目标城市，需确认是否接受"
    return 0.0, f"地区不匹配：公告地区为「{text or '未标注'}」", "异地项目，差旅与属地履约成本较高"


def industry_score(text: str, keywords: list[str]) -> tuple[float, str, str]:
    """行业关键词维度：命中任一关键词给满分。"""
    haystack = (text or "").lower()
    hits = [k for k in keywords if k and k.lower() in haystack]
    if hits:
        return 1.0, f"命中行业关键词：{', '.join(hits)}", ""
    return 0.0, "未命中行业关键词（运输/物流）", "业务相关性低，谨慎投入"


def qualification_score(notice_qual: str, company_quals: list[dict]) -> tuple[float, str, str]:
    """资质维度：命中公司已有资质满分；发现公司未持有的资质要求则扣分并提示缺项。"""
    text = notice_qual or ""
    owned = {q.get("name", "") for q in company_quals}
    text_lower = text.lower()

    hits = [name for name in owned if name and name.lower() in text_lower]
    # 公司持有"道路运输经营许可证"，通用表述也算命中
    if not hits and "道路运输经营许可证" in owned and "运输" in text:
        hits = ["道路运输经营许可证"]

    risk = ""
    score = 0.0
    if hits:
        score = 1.0
        reason = f"资质命中：{', '.join(hits)}"
    else:
        reason = "未明确要求公司已有资质"

    # 资质缺项检测：出现公司明显未持有的特殊许可
    special = ["危险货物", "危险化学品", "四级资质", "三级资质", "爆破", "冷链", "冷藏"]
    missing = [s for s in special if s in text]
    if missing:
        score = max(0.0, score - 0.6)
        risk = f"资质缺项风险：公告要求「{', '.join(missing)}」，公司当前资质可能不满足"
    return score, reason, risk


def budget_score(amount: float | None, budget_cfg: dict) -> tuple[float, str, str]:
    """预算维度（软性过滤）：区间内满分；区间外扣分并提示，但保留在简报中。"""
    if amount is None:
        return 0.4, "预算未披露", "预算未知，需人工核实项目规模"
    lo = float(budget_cfg.get("min", 0))
    hi = float(budget_cfg.get("max", float("inf")))
    if lo <= amount <= hi:
        return 1.0, f"预算在目标区间：{amount / 10000:.1f} 万元", ""
    if amount < lo:
        return 0.4, f"预算低于目标下限：{amount / 10000:.1f} 万元", "预算偏低，利润空间可能有限"
    return 0.3, f"预算超出目标上限：{amount / 10000:.1f} 万元", "超出 1-100 万预算区间，需评估履约能力"


def deadline_score(deadline, deadline_cfg: dict | None = None) -> tuple[float, str, str]:
    """截止时间维度：未过期按紧迫度给分；已过期 0 分并提示。"""
    from datetime import date
    if deadline is None:
        return 0.5, "报名截止时间未披露", "截止时间未知，需人工核实"
    days = (deadline - date.today()).days
    if days < 0:
        return 0.0, f"报名已截止（{-days} 天前）", "已过报名截止时间，不可投"
    if days <= 3:
        return 1.0, f"报名即将截止（剩余 {days} 天）", "时间紧迫，需尽快决策"
    if days <= 15:
        return 0.9, f"报名截止合理（剩余 {days} 天）", ""
    return 0.7, f"报名截止较远（剩余 {days} 天）", ""
