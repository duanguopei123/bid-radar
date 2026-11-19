"""每日简报生成：Markdown + HTML 邮件正文。

内容：今日新增项目（按匹配分排序）、每个项目 3 行摘要、截止日倒计时、原文链接。
标注「新增/更新/在库」。本模块只生成本地文件与文本，不执行任何对外动作。
"""
from __future__ import annotations

from datetime import date
from html import escape

from .models import MatchResult


def days_countdown(d: date | None, business_date: date | None = None) -> str:
    if d is None:
        return "截止日未披露"
    delta = (d - (business_date or date.today())).days
    if delta < 0:
        return f"已截止 {abs(delta)} 天"
    if delta == 0:
        return "今日截止"
    return f"剩余 {delta} 天"


def _countdown_class(d: date | None, business_date: date | None = None) -> str:
    """倒计时颜色：3 天内/已截止=红，7 天内=黄，其余=绿。"""
    if d is None:
        return "c-normal"
    delta = (d - (business_date or date.today())).days
    if delta <= 3:
        return "c-urgent"
    if delta <= 7:
        return "c-soon"
    return "c-normal"


def _change_label(change_type: str) -> str:
    return {"updated": "更新", "unchanged": "在库"}.get(change_type, "新增")


def render_markdown(
    results: list[MatchResult],
    run_date: str,
    owner_email: str,
    business_date: date | None = None,
) -> str:
    current_date = business_date or _date_from_run_date(run_date)
    display_date = current_date.isoformat()
    recommended = [r for r in results if r.recommended]
    recommended.sort(key=lambda r: r.score, reverse=True)
    lines = [
        f"# 招投标机会日报 · {display_date}",
        "",
        f"> 收件/负责人：{owner_email}　|　今日新增 {len(recommended)} 个可投项目",
        "> 本简报由只读监测系统生成，不含任何报名/提交动作；投标决策请人工确认。",
        "",
    ]
    if not recommended:
        lines.append("今日暂无新增的符合推荐阈值项目。")
        lines.append("")
        lines.append("提示：运行 `python run_once.py --all` 可查看当前全部可投项目。")
        return "\n".join(lines)

    for idx, r in enumerate(recommended, 1):
        n = r.notice
        amount = f"{n.budget_amount / 10000:.1f} 万元" if (n.budget_amount is not None and n.budget_amount > 0) else "未披露"
        lines += [
            f"## {idx}. [{_change_label(r.change_type)}] {n.title}",
            "",
            f"- **匹配分**：{r.score}/100　|　**地区**：{n.region}　|　**预算**：{amount}",
            f"- **报名截止**：{n.registration_deadline or '未披露'}"
            f"（{days_countdown(n.registration_deadline, current_date)}）"
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


_HTML_STYLE = (
    "<style>"
    "body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;max-width:760px;"
    "margin:0 auto;padding:16px;color:#1f2328;line-height:1.65;background:#f7f8fa}"
    "h1{font-size:20px;margin:8px 0 6px}"
    ".sub{color:#6b7280;font-size:13px;margin:0 0 4px}"
    ".stat{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:10px 14px;"
    "margin:12px 0 4px;font-size:13px;color:#374151}"
    ".card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin:12px 0}"
    "h2{font-size:16px;margin:0 0 10px;line-height:1.45}"
    ".meta{color:#6b7280;font-size:13px;margin:4px 0}"
    ".score{color:#c53030;font-weight:bold;font-size:17px}"
    ".tag{display:inline-block;background:#ebf4ff;color:#2b6cb0;padding:2px 8px;border-radius:10px;"
    "font-size:12px;margin-right:6px;vertical-align:middle}"
    ".field{color:#374151;font-size:13px;margin:4px 0}"
    ".summary{font-size:14px;margin:10px 0;color:#1f2328}"
    ".risk{color:#9a3412;background:#fff7ed;border-radius:6px;padding:8px 10px;font-size:13px;margin:8px 0}"
    ".reason{color:#4b5563;font-size:13px;margin:6px 0}"
    ".countdown{font-weight:bold}"
    ".c-urgent{color:#c53030}.c-soon{color:#b7791f}.c-normal{color:#2f855a}"
    "a{color:#2b6cb0;word-break:break-all}"
    ".foot{color:#9ca3af;font-size:12px;text-align:center;margin:20px 0 8px}"
    "@media (max-width:480px){body{padding:10px}h1{font-size:18px}.card{padding:12px}}"
    "</style>"
)


def render_html(
    results: list[MatchResult],
    run_date: str,
    owner_email: str,
    business_date: date | None = None,
) -> str:
    current_date = business_date or _date_from_run_date(run_date)
    display_date = current_date.isoformat()
    recommended = [r for r in results if r.recommended]
    recommended.sort(key=lambda r: r.score, reverse=True)
    esc = escape
    urgent = sum(1 for r in recommended
                 if r.notice.registration_deadline
                 and (r.notice.registration_deadline - current_date).days <= 3)
    total = len(recommended)

    parts = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        _HTML_STYLE,
        "</head><body>",
        f"<h1>招投标机会日报 · {esc(display_date)}</h1>",
        f"<p class='sub'>负责人：{esc(owner_email)}</p>",
        f"<div class='stat'>本次可投 <b>{total}</b> 个　|　"
        f"3 天内截止 <b class='c-urgent'>{urgent}</b> 个　|　"
        "只读监测，投标决策须人工确认</div>",
    ]

    if not recommended:
        parts.append("<div class='card'><p>今日暂无新增的符合推荐阈值项目。</p>"
                     "<p class='meta'>提示：运行 <code>python run_once.py --all</code> "
                     "可查看当前全部可投项目。</p></div>")

    for r in recommended:
        n = r.notice
        amount = (f"{n.budget_amount / 10000:.1f} 万元"
                  if (n.budget_amount is not None and n.budget_amount > 0) else "未披露")
        parts.append("<div class='card'>")
        parts.append(
            f"<h2><span class='tag'>{_change_label(r.change_type)}</span>{esc(n.title)}</h2>"
            f"<p class='meta'>匹配分 <span class='score'>{r.score}</span>/100"
            f"　|　地区：{esc(n.region)}　|　预算：{amount}</p>"
            f"<p class='field'>报名截止：{esc(str(n.registration_deadline or '未披露'))}"
            f"　<span class='countdown {_countdown_class(n.registration_deadline, current_date)}'>"
            f"（{days_countdown(n.registration_deadline, current_date)}）</span>"
            f"　|　开标：{esc(str(n.bid_open_time or '未披露'))}</p>"
            f"<p class='field'>采购人：{esc(n.purchaser)}</p>"
        )
        parts.append("<p class='summary'>" + esc(r.summary).replace("\n", "<br>") + "</p>")
        parts.append("<p class='reason'>匹配理由：" + esc("；".join(r.reasons)) + "</p>")
        if r.risks:
            parts.append("<p class='risk'>风险提示：" + esc("；".join(r.risks)) + "</p>")
        parts.append(
            f"<p class='meta'><a href='{esc(n.source_url)}'>查看原文公告</a>"
            f"　<span class='foot' style='text-align:left;margin:0'>来源 {esc(n.source)}"
            f" · 抓取 {esc(n.fetched_at.isoformat())}</span></p>"
        )
        parts.append("</div>")

    parts.append("<p class='foot'>本简报由只读监测系统生成，不含报名/提交动作</p>")
    parts.append("</body></html>")
    return "".join(parts)


def _date_from_run_date(run_date: str) -> date:
    try:
        return date.fromisoformat(run_date)
    except ValueError:
        return date.today()
