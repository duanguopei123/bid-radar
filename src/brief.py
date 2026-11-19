"""每日简报生成：Markdown + HTML 邮件正文。

内容：今日新增项目（按匹配分排序）、每个项目 3 行摘要、截止日倒计时、原文链接。
标注「新增/更新/在库」。本模块只生成本地文件与文本，不执行任何对外动作。
"""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import MatchResult

# 简报里一切时间都按这个时区展示：带时区的时间先换算，裸时间视为已经是本地时间
DEFAULT_DISPLAY_TZ = "Asia/Shanghai"


def _resolve_tz(name: str | None):
    try:
        return ZoneInfo(name or DEFAULT_DISPLAY_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def fmt_dt(value: datetime | None, tz_name: str | None = None) -> str:
    """把时间统一成「YYYY-MM-DD HH:MM」，不向外暴露 +00:00 这类原始偏移。

    - 带时区：换算到 tz_name（默认北京时间）后格式化
    - 不带时区：视为已是本地时间，原样格式化
    - 空值：返回「未披露」，与其它字段的空值写法一致
    """
    if value is None:
        return "未披露"
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is not None:
        tz = _resolve_tz(tz_name)
        if tz is not None:
            value = value.astimezone(tz)
    return value.strftime("%Y-%m-%d %H:%M")


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
    display_tz: str | None = None,
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
            f"　|　**开标**：{fmt_dt(n.bid_open_time, display_tz)}",
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
            f"<!-- 来源：{n.source} | 抓取时间：{fmt_dt(n.fetched_at, display_tz)} | 公告ID：{n.notice_id} -->",
            "",
            "---",
            "",
        ]
    return "\n".join(lines)


def render_push_summary(
    results: list[MatchResult],
    run_date: str,
    owner_email: str = "",
    business_date: date | None = None,
) -> str:
    """手机推送专用的短摘要：一屏读完，点标题可跳原文。

    完整简报（含逐条匹配理由与风险）仍在 out/ 目录的 HTML 里；
    微信只需要「今天有几个能投、最急的是哪个、链接在哪」。
    """
    current_date = business_date or _date_from_run_date(run_date)
    display_date = current_date.isoformat()
    recommended = [r for r in results if r.recommended]
    recommended.sort(key=lambda r: (r.notice.registration_deadline or date.max, -r.score))

    urgent = sum(
        1
        for r in recommended
        if r.notice.registration_deadline is not None
        and 0 <= (r.notice.registration_deadline - current_date).days <= 3
    )

    lines = [
        f"**招投标机会日报 · {display_date}**",
        "",
        f"今日可投 **{len(recommended)}** 个 | 3 天内截止 **{urgent}** 个",
        "",
    ]

    if not recommended:
        lines += [
            "今日暂无新增的符合推荐阈值项目。",
            "",
            "（只读监测，投标决策请人工确认）",
        ]
        return "\n".join(lines)

    for idx, r in enumerate(recommended, 1):
        n = r.notice
        amount = (
            f"{n.budget_amount / 10000:.0f}万"
            if (n.budget_amount is not None and n.budget_amount > 0)
            else "预算未披露"
        )
        deadline = n.registration_deadline
        when = f"{deadline}（{days_countdown(deadline, current_date)}）" if deadline else "截止未披露"
        title = " ".join((n.title or "").split())
        lines += [
            f"**{idx}. {title}**",
            f"{r.score}分 · {n.region or '地区未披露'} · {amount}",
            f"截止：{when}",
            f"[查看原文]({n.source_url})",
            "",
        ]

    lines += [
        "---",
        "（只读监测，不含报名/提交；投标决策请人工确认）",
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
    display_tz: str | None = None,
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
            f"　|　开标：{esc(fmt_dt(n.bid_open_time, display_tz))}</p>"
            f"<p class='field'>采购人：{esc(n.purchaser)}</p>"
        )
        parts.append("<p class='summary'>" + esc(r.summary).replace("\n", "<br>") + "</p>")
        parts.append("<p class='reason'>匹配理由：" + esc("；".join(r.reasons)) + "</p>")
        if r.risks:
            parts.append("<p class='risk'>风险提示：" + esc("；".join(r.risks)) + "</p>")
        parts.append(
            f"<p class='meta'><a href='{esc(n.source_url)}'>查看原文公告</a>"
            f"　<span class='foot' style='text-align:left;margin:0'>来源 {esc(n.source)}"
            f" · 抓取 {esc(fmt_dt(n.fetched_at, display_tz))}</span></p>"
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
