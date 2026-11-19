"""每日简报生成：Markdown + HTML 邮件正文。

内容：今日新增项目（按匹配分排序）、每个项目 3 行摘要、截止日倒计时、原文链接。
标注「新增/更新」。本模块只生成本地文件与文本，不执行任何对外动作。
"""
from __future__ import annotations

from datetime import date
from html import escape

from .models import MatchResult


def days_countdown(d: date | None) -> str:
    if d is None:
        return "截止日未披露"
    delta = (d - date.today()).days
    if delta < 0:
        return f"已截止 {abs(delta)} 天"
    if delta == 0:
        return "今日截止"
    return f"剩余 {delta} 天"


def _change_label(change_type: str) -> str:
    return "更新" if change_type == "updated" else "新增"


def render_markdown(results: list[MatchResult], run_date: str, owner_email: str) -> str:
    recommended = [r for r in results if r.recommended]
    recommended.sort(key=lambda r: r.score, reverse=True)
    lines = [
        f"# 招投标机会日报 · {run_date}",
        "",
        f"> 收件/负责人：{owner_email}　|　今日新增 {len(recommended)} 个可投项目",
        "> 本简报由只读监测系统生成，不含任何报名/提交动作；投标决策请人工确认。",
        "",
    ]
    if not recommended:
        lines.append("今日暂无符合推荐阈值的项目。")
        return "\n".join(lines)

    for idx, r in enumerate(recommended, 1):
        n = r.notice
        amount = f"{n.budget_amount / 10000:.1f} 万元" if n.budget_amount else "未披露"
        lines += [
            f"## {idx}. [{_change_label(r.change_type)}] {n.title}",
            "",
            f"- **匹配分**：{r.score}/100　|　**地区**：{n.region}　|　**预算**：{amount}",
            f"- **报名截止**：{n.registration_deadline or '未披露'}（{days_countdown(n.registration_deadline)}）"
            f"　|　**开标**：{n.bid_open_time or '未披露'}",
            f"- **采购人**：{n.purchaser}",
            "",
            "**3 行摘要**",
            "",
            r.summary,
            "",
            "**匹配理由**",
            "",
        ]
        lines += [f"- {reason}" for reason in r.reasons]
        if r.risks:
            lines += ["", "**风险提示**", ""]
            lines += [f"- {risk}" for risk in r.risks]
        lines += [
            "",
            f"**原文链接**：{n.source_url}",
            "",
            f"<!-- 来源：{n.source} | 抓取时间：{n.fetched_at.isoformat()} | 公告ID：{n.notice_id} -->",
            "",
            "---",
            "",
        ]
    return "\n".join(lines)


def render_html(results: list[MatchResult], run_date: str, owner_email: str) -> str:
    recommended = [r for r in results if r.recommended]
    recommended.sort(key=lambda r: r.score, reverse=True)
    esc = escape
    parts = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
        "<style>body{font-family:-apple-system,'Microsoft YaHei',sans-serif;max-width:820px;margin:auto;color:#222;line-height:1.6}"
        "h1{font-size:22px}h2{font-size:17px;border-left:4px solid #2b6cb0;padding-left:8px}"
        ".meta{color:#666;font-size:13px}.score{color:#c53030;font-weight:bold}"
        ".tag{display:inline-block;background:#ebf4ff;color:#2b6cb0;padding:1px 6px;border-radius:4px;font-size:12px}"
        ".risk{color:#c05621}a{color:#2b6cb0}.card{border-bottom:1px solid #eee;padding:12px 0}</style>",
        "</head><body>",
        f"<h1>招投标机会日报 · {run_date}</h1>",
        f"<p class='meta'>负责人：{esc(owner_email)}　|　今日新增 {len(recommended)} 个可投项目<br>"
        "本简报由只读监测系统生成，不含报名/提交动作；投标决策请人工确认。</p>",
    ]
    if not recommended:
        parts.append("<p>今日暂无符合推荐阈值的项目。</p>")
    for r in recommended:
        n = r.notice
        amount = f"{n.budget_amount / 10000:.1f} 万元" if n.budget_amount else "未披露"
        parts.append("<div class='card'>")
        parts.append(
            f"<h2><span class='tag'>{_change_label(r.change_type)}</span> {esc(n.title)}</h2>"
            f"<p class='meta'>匹配分 <span class='score'>{r.score}</span>/100　|　地区：{esc(n.region)}　|　预算：{amount}</p>"
            f"<p class='meta'>报名截止：{esc(str(n.registration_deadline or '未披露'))}"
            f"（{days_countdown(n.registration_deadline)}）　|　开标：{esc(str(n.bid_open_time or '未披露'))}</p>"
            f"<p class='meta'>采购人：{esc(n.purchaser)}</p>"
        )
        parts.append("<p>" + esc(r.summary).replace("\n", "<br>") + "</p>")
        parts.append("<p class='meta'>匹配理由：" + esc("；".join(r.reasons)) + "</p>")
        if r.risks:
            parts.append("<p class='risk'>风险提示：" + esc("；".join(r.risks)) + "</p>")
        parts.append(
            f"<p><a href='{esc(n.source_url)}'>查看原文公告</a>　"
            f"<span class='meta'>来源 {esc(n.source)} · 抓取 {esc(n.fetched_at.isoformat())}</span></p>"
        )
        parts.append("</div>")
    parts.append("</body></html>")
    return "".join(parts)
