"""工作台自检：一次把「环境 / 配置 / 推送 / 定时任务 / 最近运行结果」查清楚。

用途：用户点「自检」后能自己看出问题在哪，不必逐个去问。
输出只用 [OK] / [!!] / [--] 三种前缀，避免中文在 GBK 控制台里出错。
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

OK, WARN, INFO = "[OK]", "[!!]", "[--]"

# 计划任务名与桌面软件保持一致，避免两边写死不同名字
try:
    from settings_gui import TASK_NAME  # type: ignore
except Exception:  # tkinter 缺失时仍能自检
    TASK_NAME = "招投标工作台-每日9点"

problems: list[str] = []


def line(prefix: str, text: str) -> None:
    print(f"{prefix} {text}")


def section(title: str) -> None:
    print()
    print(f"== {title} ==")


def check_python() -> None:
    section("Python 环境")
    exe = Path(sys.executable)
    line(INFO, f"解释器：{exe}")
    in_venv = ".venv" in str(exe).lower()
    if in_venv:
        line(OK, "正运行在项目自带的 .venv 里")
    else:
        line(WARN, "当前不是 .venv 里的解释器；直接双击 自检.bat 才是正确方式")
        problems.append("解释器不是 .venv，可能缺依赖")

    missing = []
    for mod in ("yaml", "requests", "jinja2", "apscheduler", "dotenv"):
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if missing:
        line(WARN, "缺少依赖：" + "、".join(missing))
        problems.append("依赖缺失：" + "、".join(missing))
    else:
        line(OK, "依赖齐全（yaml / requests / jinja2 / apscheduler / dotenv）")


def check_company() -> None:
    section("公司画像")
    try:
        from src.config import load_config
        cfg = load_config()
    except Exception as exc:
        line(WARN, f"配置加载失败：{exc}")
        problems.append(f"配置加载失败：{exc}")
        return

    company = cfg.get("company", {})
    name = company.get("name", "")
    line(OK if name else WARN, f"公司名称：{name or '未填写'}")
    if not name:
        problems.append("公司名称未填写")

    kws = company.get("industry_keywords") or []
    line(OK if kws else WARN, f"行业关键词（{len(kws)} 个）：{'、'.join(map(str, kws)) or '未填写'}")
    if not kws:
        problems.append("行业关键词为空，会把无关公告都当成不匹配")

    regions = company.get("regions") or []
    line(OK if regions else WARN, f"服务区域：{'、'.join(map(str, regions)) or '未填写'}")

    quals = [q.get("name", "") if isinstance(q, dict) else str(q)
             for q in (company.get("qualifications") or [])]
    line(OK if quals else WARN, f"资质（{len(quals)} 项）：{'、'.join(quals) or '未填写'}")

    budget = company.get("budget") or {}
    lo = budget.get("min")
    hi = budget.get("max")
    if lo is None and hi is None:
        line(WARN, "预算区间：未设置（不设上限会推来几千万的项目）")
        problems.append("预算区间未设置")
    else:
        line(OK, f"预算区间：{(lo or 0) / 10000:.0f} 万 ~ {(hi or 0) / 10000:.0f} 万")

    src = "company.yaml（桌面软件写入）" if (ROOT / "company.yaml").exists() else "config.yaml"
    line(INFO, f"配置来源：{src}")


def check_notifier() -> None:
    section("推送到手机")
    env_path = ROOT / ".env"
    if not env_path.exists():
        line(WARN, ".env 不存在，推送会一直处于 skipped")
        line(INFO, "做一次：双击 3-工作台设置，选渠道、填 Token、点保存")
        problems.append(".env 未创建，没有配置任何推送渠道")
        return

    try:
        from src.config import load_config
        cfg = load_config()
    except Exception:
        return

    channel = (cfg.get("notifier") or {}).get("channel", "none")
    labels = {
        "serverchan": "微信 · Server酱",
        "pushplus": "微信 · PushPlus",
        "wecom_webhook": "企业微信 · 群机器人",
        "none": "未启用（只生成电脑上的简报）",
    }
    line(OK if channel != "none" else WARN, f"当前渠道：{labels.get(channel, channel)}")

    keys = {
        "serverchan": "SERVERCHAN_SENDKEY",
        "pushplus": "PUSHPLUS_TOKEN",
        "wecom_webhook": "WECOM_WEBHOOK_URL",
    }
    key = keys.get(channel)
    if key:
        value = os.getenv(key, "")
        if value:
            masked = value[:4] + "*" * max(0, len(value) - 8) + value[-4:] if len(value) > 8 else "****"
            line(OK, f"{key} 已填写：{masked}")
        else:
            line(WARN, f"{key} 为空，推送会被跳过")
            problems.append(f"{key} 为空")

    if channel == "none":
        problems.append("未启用推送渠道")


def check_schedule() -> None:
    section("每天 9 点自动运行")
    cmd = ["schtasks", "/query", "/tn", TASK_NAME]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        line(WARN, f"无法查询计划任务：{exc}")
        return
    if proc.returncode == 0:
        line(OK, f"计划任务已注册（{TASK_NAME}）")
        line(INFO, "注意：电脑关机或休眠时不会运行")
    else:
        line(WARN, "计划任务未注册")
        line(INFO, "做一次：双击 3-工作台设置 → 点「设为每天 9:00」")
        problems.append("每日定时未注册")


def check_database() -> None:
    section("数据与最近运行")
    try:
        from src.config import load_config
        cfg = load_config()
        db_path = Path(cfg["app"]["db_path"])
    except Exception:
        db_path = ROOT / "data" / "bidding.db"

    if not db_path.exists():
        line(WARN, f"数据库不存在：{db_path}")
        line(INFO, "双击 启动工作台 跑一次就会创建")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        notices = conn.execute("SELECT COUNT(*) FROM notices").fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM briefs").fetchone()[0]
        line(OK, f"数据库：{db_path.name}　历史公告 {notices} 条　简报 {runs} 份")

        row = conn.execute(
            """SELECT b.run_date, b.item_count, d.status
               FROM briefs b LEFT JOIN brief_deliveries d ON d.brief_id = b.id
               ORDER BY b.id DESC LIMIT 1"""
        ).fetchone()
        if row:
            status_label = {
                "sent": "已推送", "pending": "待推送", "failed": "推送失败（下次会重试）",
                "skipped": "未推送（渠道未启用）", "sending": "推送中",
            }.get(row["status"], row["status"] or "未知")
            line(OK, f"最近一份简报：{row['run_date']}，{row['item_count']} 个项目，{status_label}")
        else:
            line(INFO, "还没有生成过简报")

        retry = conn.execute(
            "SELECT COUNT(*) FROM notice_processing WHERE status IN ('pending','failed')"
        ).fetchone()[0]
        if retry:
            line(INFO, f"有 {retry} 条公告待下次重试处理（正常现象，下次运行会自动补）")
    finally:
        conn.close()

    out_dir = ROOT / "out"
    if out_dir.exists():
        briefs = sorted(out_dir.glob("brief_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if briefs:
            latest = briefs[0]
            line(OK, f"最新简报文件：{latest.relative_to(ROOT)}")


def main() -> int:
    print("=" * 56)
    print(" 招投标工作台 · 自检")
    print("=" * 56)

    check_python()
    check_company()
    check_notifier()
    check_schedule()
    check_database()

    print()
    print("=" * 56)
    if problems:
        print(f" 发现 {len(problems)} 项待处理：")
        for idx, item in enumerate(problems, 1):
            print(f"   {idx}. {item}")
    else:
        print(" 全部检查通过，工作台可以直接用。")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
