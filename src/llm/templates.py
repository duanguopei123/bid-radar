"""模板兜底：无 LLM key 或调用失败时生成 3 行摘要，保证离线可跑通。"""
from __future__ import annotations

from ..models import MatchResult
from .base import LLMProvider


def template_summary(result: MatchResult) -> str:
    n = result.notice
    amount = f"{n.budget_amount / 10000:.1f} 万元" if n.budget_amount else "未披露"
    deadline = n.registration_deadline.isoformat() if n.registration_deadline else "未披露"
    top_reasons = "；".join(r.split("] ", 1)[-1] for r in result.reasons[:2])
    risk_part = ("风险：" + "；".join(result.risks[:2])) if result.risks else "风险：暂未发现明显缺项"
    return (
        f"项目：{n.title}，采购人 {n.purchaser}，预算 {amount}。\n"
        f"匹配：{result.score} 分，{top_reasons}。\n"
        f"提示：报名截止 {deadline}，{risk_part}。"
    )


class TemplateProvider(LLMProvider):
    def summarize(self, result: MatchResult) -> str:
        return template_summary(result)
