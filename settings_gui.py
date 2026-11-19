"""招投标工作台 · 公司设置

用途：不懂代码也能改公司信息、换行业、配微信推送、设每天自动运行。
写入范围只有两处，绝不碰 config.yaml（保护里面的注释与高级设置）：
  1. company.yaml  —— 公司画像（名称/关键词/区域/资质/预算）
  2. .env          —— 推送渠道与 token

启动方式：双击项目根目录下的「配置工作台.bat」。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import tkinter as tk
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText

import yaml

ROOT = Path(__file__).resolve().parent
COMPANY_YAML = ROOT / "company.yaml"
ENV_PATH = ROOT / ".env"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
TASK_NAME = "招投标工作台-每日9点"

# 渠道：(配置值, 界面显示, 对应环境变量名)
CHANNELS = [
    ("none", "不推送（只在电脑上生成网页简报）", ""),
    ("serverchan", "微信 · Server酱（推荐，免费 5 条/天，无需实名）", "SERVERCHAN_SENDKEY"),
    ("pushplus", "微信 · PushPlus（需实名，实名后 200 条/天）", "PUSHPLUS_TOKEN"),
    ("wecom_webhook", "企业微信 · 群机器人（消息到企业微信 App）", "WECOM_WEBHOOK_URL"),
]

BG = "#f4f6f8"
CARD = "#ffffff"
BORDER = "#dde3ea"
TEXT = "#1f2328"
MUTED = "#6b7280"
ACCENT = "#2b6cb0"
OKC = "#2f855a"
ERRC = "#c53030"
FONT = ("Microsoft YaHei UI", 10)
FONT_B = ("Microsoft YaHei UI", 10, "bold")
FONT_H = ("Microsoft YaHei UI", 14, "bold")


# ---------------- 读写 ----------------

def read_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if not ENV_PATH.exists():
        return data
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def write_env(updates: dict[str, str]) -> None:
    """只改指定键，保留其余行与注释。首次创建时继承 .env.example 的模板。"""
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    else:
        example = ROOT / ".env.example"
        if example.exists():
            lines = example.read_text(encoding="utf-8").splitlines()
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            key = s.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}")
                continue
        out.append(line)
    if remaining:
        if out and out[-1].strip():
            out.append("")
        for k, v in remaining.items():
            out.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def load_company() -> dict:
    """以 config.yaml 的 company 段为底，company.yaml 覆盖其上。"""
    base: dict = {}
    cfg_path = ROOT / "config.yaml"
    if cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        base = dict(raw.get("company") or {})
    if COMPANY_YAML.exists():
        over = yaml.safe_load(COMPANY_YAML.read_text(encoding="utf-8")) or {}
        if isinstance(over, dict):
            base.update(over)
    return base


def save_company(name: str, keywords: list[str], regions: list[str],
                 quals: list[str], bmin: int, bmax: int) -> None:
    data = {
        "name": name,
        "industry_keywords": keywords,
        "regions": regions,
        "qualifications": [
            {"code": f"qual_{i + 1}", "name": q}
            for i, q in enumerate(quals)
        ],
        "budget": {"min": bmin, "max": bmax},
        "budget_soft_filter": True,
    }
    header = (
        "# 公司画像（由「工作台设置」软件自动生成）\n"
        "# 换公司、换行业时改这里即可；也可以直接双击「工作台设置」用界面改。\n"
        "# 注意：本文件会覆盖 config.yaml 中的 company 段。\n\n"
    )
    COMPANY_YAML.write_text(
        header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def split_lines(text: str) -> list[str]:
    items: list[str] = []
    for raw in text.replace("，", ",").replace("、", ",").splitlines():
        for part in raw.split(","):
            part = part.strip()
            if part and part not in items:
                items.append(part)
    return items


# ---------------- 界面 ----------------

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("招投标工作台 · 公司设置")
        root.geometry("780x820")
        root.minsize(720, 700)
        root.configure(bg=BG)

        self.company = load_company()
        self.env = read_env()

        outer = tk.Frame(root, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(outer, text="招投标工作台 · 公司设置", font=FONT_H, bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(
            outer,
            text="改完点「保存」即生效；换公司、换行业只需要改这一页。",
            font=("Microsoft YaHei UI", 9), bg=BG, fg=MUTED,
        ).pack(anchor="w", pady=(2, 10))

        self._build_company_card(outer)
        self._build_push_card(outer)
        self._build_actions(outer)
        self._build_log(outer)

        self._fill_from_config()

    # ---- 卡片容器 ----
    def _card(self, parent, title: str) -> tk.Frame:
        box = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="x", pady=(0, 12))
        tk.Label(box, text=title, font=FONT_B, bg=CARD, fg=TEXT).pack(anchor="w", padx=14, pady=(12, 6))
        inner = tk.Frame(box, bg=CARD)
        inner.pack(fill="x", padx=14, pady=(0, 14))
        return inner

    def _field(self, parent, label: str, row: int, widget: tk.Widget, hint: str = "") -> tk.Label | None:
        tk.Label(parent, text=label, font=FONT, bg=CARD, fg=MUTED).grid(
            row=row, column=0, sticky="nw", pady=6, padx=(0, 10)
        )
        widget.grid(row=row, column=1, sticky="ew", pady=6)
        if hint:
            lbl = tk.Label(parent, text=hint, font=("Microsoft YaHei UI", 8), bg=CARD, fg="#9ca3af")
            lbl.grid(row=row + 1, column=1, sticky="w", pady=(0, 4))
            return lbl
        return None

    def _entry(self, parent, value: str = "") -> tk.Entry:
        e = tk.Entry(parent, font=FONT, bg="#fbfcfd", fg=TEXT, relief="solid", bd=1,
                     highlightthickness=0, insertbackground=TEXT)
        e.insert(0, value)
        return e

    def _text(self, parent, height: int = 3) -> tk.Text:
        t = tk.Text(parent, font=FONT, height=height, bg="#fbfcfd", fg=TEXT,
                    relief="solid", bd=1, highlightthickness=0, wrap="word",
                    insertbackground=TEXT)
        return t

    # ---- 公司信息 ----
    def _build_company_card(self, parent) -> None:
        inner = self._card(parent, "① 公司信息")
        inner.columnconfigure(1, weight=1)

        self.e_name = self._entry(inner)
        self._field(inner, "公司名称", 0, self.e_name)

        self.t_keywords = self._text(inner, 3)
        self._field(inner, "主营 / 行业词", 1, self.t_keywords,
                    "一行一个。公告标题里出现这些词就加分。例：运输、物流、货运、大件")

        self.t_regions = self._text(inner, 3)
        self._field(inner, "服务区域", 3, self.t_regions,
                    "一行一个。例：徐州、江苏省（填到市级命中率更高）")

        self.t_quals = self._text(inner, 3)
        self._field(inner, "公司资质", 5, self.t_quals,
                    "一行一个，照证书上的名字写。例：道路运输经营许可证")

        budget = tk.Frame(inner, bg=CARD)
        budget.grid(row=7, column=1, sticky="w", pady=6)
        self.e_bmin = tk.Entry(budget, font=FONT, width=10, bg="#fbfcfd", fg=TEXT,
                               relief="solid", bd=1, highlightthickness=0)
        self.e_bmin.pack(side="left")
        tk.Label(budget, text="  万元 ～  ", font=FONT, bg=CARD, fg=MUTED).pack(side="left")
        self.e_bmax = tk.Entry(budget, font=FONT, width=10, bg="#fbfcfd", fg=TEXT,
                               relief="solid", bd=1, highlightthickness=0)
        self.e_bmax.pack(side="left")
        tk.Label(budget, text="  万元", font=FONT, bg=CARD, fg=MUTED).pack(side="left")
        tk.Label(inner, text="可承接预算区间", font=FONT, bg=CARD, fg=MUTED).grid(
            row=7, column=0, sticky="nw", pady=6, padx=(0, 10)
        )

    # ---- 推送 ----
    def _build_push_card(self, parent) -> None:
        inner = self._card(parent, "② 每天推送到手机")
        inner.columnconfigure(1, weight=1)

        self.var_channel = tk.StringVar()
        combo = tk.OptionMenu(inner, self.var_channel, *[c[1] for c in CHANNELS],
                              command=lambda _v: self._on_channel_change())
        combo.config(font=("Microsoft YaHei UI", 9), bg="#fbfcfd", fg=TEXT,
                     relief="solid", bd=1, highlightthickness=0, anchor="w")
        combo.grid(row=0, column=1, sticky="ew", pady=6)
        tk.Label(inner, text="推送方式", font=FONT, bg=CARD, fg=MUTED).grid(
            row=0, column=0, sticky="nw", pady=6, padx=(0, 10)
        )

        self.e_token = self._entry(inner)
        self.lbl_token_hint = self._field(inner, "Token / 地址", 1, self.e_token, self._token_hint())

        tk.Label(inner, text="每天自动运行", font=FONT, bg=CARD, fg=MUTED).grid(
            row=3, column=0, sticky="w", pady=6, padx=(0, 10)
        )
        sched = tk.Frame(inner, bg=CARD)
        sched.grid(row=3, column=1, sticky="w", pady=6)
        tk.Button(sched, text="设为每天 9:00", font=("Microsoft YaHei UI", 9),
                  bg="#eef2f7", fg=TEXT, relief="flat", padx=12, pady=4,
                  cursor="hand2", command=self.on_schedule).pack(side="left")
        tk.Button(sched, text="取消自动运行", font=("Microsoft YaHei UI", 9),
                  bg="#f7f7f7", fg=MUTED, relief="flat", padx=12, pady=4,
                  cursor="hand2", command=self.on_unschedule).pack(side="left", padx=8)
        tk.Label(inner, text="注意：电脑需在 9 点前开机且未休眠，关机当天不会推送。",
                 font=("Microsoft YaHei UI", 8), bg=CARD, fg="#9ca3af").grid(
            row=4, column=1, sticky="w"
        )

    def _token_hint(self) -> str:
        cur = self._channel_code()
        if cur == "serverchan":
            return "到 sct.ftqq.com 微信扫码登录 → 复制 SendKey（SCT 开头）"
        if cur == "pushplus":
            return "到 pushplus.plus 微信扫码登录并实名 → 复制 token"
        if cur == "wecom_webhook":
            return "企业微信群 → 群机器人 → 添加 → 复制 Webhook 地址"
        return "不需要填写"

    def _channel_code(self) -> str:
        label = self.var_channel.get()
        for code, text, _env in CHANNELS:
            if text == label:
                return code
        return "none"

    def _on_channel_change(self) -> None:
        if getattr(self, "lbl_token_hint", None) is not None:
            self.lbl_token_hint.config(text=self._token_hint())
        code = self._channel_code()
        env_key = next((e for c, _t, e in CHANNELS if c == code), "")
        self.e_token.delete(0, "end")
        if env_key:
            self.e_token.insert(0, self.env.get(env_key, ""))

    # ---- 操作区 ----
    def _build_actions(self, parent) -> None:
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", pady=(0, 8))

        def mk(text: str, cmd, bg: str, fg: str):
            b = tk.Button(bar, text=text, font=FONT_B, bg=bg, fg=fg, relief="flat",
                          padx=18, pady=8, cursor="hand2", command=cmd,
                          activebackground=bg, activeforeground=fg)
            b.pack(side="left", padx=(0, 10))
            return b

        mk("保存设置", self.on_save, ACCENT, "#ffffff")
        mk("发一条测试推送", self.on_test_push, "#eef2f7", TEXT)
        mk("立即运行一次", self.on_run, "#eef2f7", TEXT)
        tk.Button(bar, text="打开最新简报", font=("Microsoft YaHei UI", 9), bg=BG, fg=ACCENT,
                  relief="flat", cursor="hand2", command=self.on_open_brief).pack(side="right")

    def _build_log(self, parent) -> None:
        tk.Label(parent, text="运行日志", font=("Microsoft YaHei UI", 9), bg=BG, fg=MUTED).pack(anchor="w")
        self.log = ScrolledText(parent, height=9, font=("Consolas", 9), bg="#ffffff",
                                fg=TEXT, relief="solid", bd=1, highlightthickness=0)
        self.log.pack(fill="both", expand=True, pady=(4, 0))
        self._say("准备就绪。改完信息点「保存设置」，再点「发一条测试推送」确认手机能收到。")

    # ---- 填充 ----
    def _fill_from_config(self) -> None:
        c = self.company
        self.e_name.insert(0, c.get("name", ""))
        self.t_keywords.insert("1.0", "\n".join(c.get("industry_keywords", [])))
        self.t_regions.insert("1.0", "\n".join(c.get("regions", [])))
        self.t_quals.insert("1.0", "\n".join(
            q.get("name", "") for q in (c.get("qualifications") or []) if isinstance(q, dict)
        ))
        budget = c.get("budget") or {}
        self.e_bmin.insert(0, str(int((budget.get("min") or 0) / 10000)))
        self.e_bmax.insert(0, str(int((budget.get("max") or 0) / 10000)))

        ch = self.env.get("NOTIFIER_CHANNEL", "none")
        label = next((t for code, t, _e in CHANNELS if code == ch), CHANNELS[0][1])
        self.var_channel.set(label)
        env_key = next((e for code, _t, e in CHANNELS if code == ch), "")
        if env_key:
            self.e_token.insert(0, self.env.get(env_key, ""))
        if getattr(self, "lbl_token_hint", None) is not None:
            self.lbl_token_hint.config(text=self._token_hint())

    # ---- 日志 ----
    def _say(self, msg: str) -> None:
        self.log.insert("end", msg.rstrip() + "\n")
        self.log.see("end")
        self.root.update_idletasks()

    # ---- 动作 ----
    def _collect(self) -> tuple[bool, str]:
        name = self.e_name.get().strip()
        if not name:
            return False, "公司名称不能为空"
        keywords = split_lines(self.t_keywords.get("1.0", "end"))
        if not keywords:
            return False, "主营/行业词至少填一个"
        regions = split_lines(self.t_regions.get("1.0", "end"))
        if not regions:
            return False, "服务区域至少填一个"
        try:
            bmin = int(float(self.e_bmin.get() or 0) * 10000)
            bmax = int(float(self.e_bmax.get() or 0) * 10000)
        except ValueError:
            return False, "预算只能填数字（单位：万元）"
        if bmin > bmax:
            return False, "预算下限不能大于上限"
        return True, ""

    def on_save(self) -> None:
        ok, err = self._collect()
        if not ok:
            messagebox.showwarning("还没填完", err)
            return
        save_company(
            self.e_name.get().strip(),
            split_lines(self.t_keywords.get("1.0", "end")),
            split_lines(self.t_regions.get("1.0", "end")),
            split_lines(self.t_quals.get("1.0", "end")),
            int(float(self.e_bmin.get() or 0) * 10000),
            int(float(self.e_bmax.get() or 0) * 10000),
        )
        code = self._channel_code()
        env_key = next((e for c, _t, e in CHANNELS if c == code), "")
        updates = {"NOTIFIER_CHANNEL": code}
        if env_key:
            updates[env_key] = self.e_token.get().strip()
        write_env(updates)
        self.env = read_env()
        self._say(f"[已保存] 公司：{self.e_name.get().strip()}")
        self._say(f"[已保存] 推送方式：{self.var_channel.get()}")
        if code != "none" and not self.e_token.get().strip():
            self._say("[提醒] 还没填 Token，暂时不会真的推送到手机。")

    def on_test_push(self) -> None:
        code = self._channel_code()
        if code == "none":
            messagebox.showinfo("不需要测试", "当前是「不推送」模式，只在电脑上生成简报。")
            return
        token = self.e_token.get().strip()
        if not token:
            messagebox.showwarning("缺 Token", "请先填 Token 并点「保存设置」。")
            return
        self._say("正在发送测试消息…")
        try:
            sys.path.insert(0, str(ROOT))
            from src.notifier.factory import build_notifier  # noqa: PLC0415

            cfg = {"notifier": {"channel": code}}
            key = {"serverchan": "serverchan_sendkey",
                   "pushplus": "pushplus_token",
                   "wecom_webhook": "webhook_url"}[code]
            cfg["notifier"][key] = token
            notifier = build_notifier(cfg)
            ok = bool(notifier and notifier.send(
                "招投标工作台 · 测试消息",
                "**这是一条测试推送。**\n\n收到说明配置正确，明天早上 9 点会自动推日报。",
            ))
        except Exception as exc:  # noqa: BLE001
            self._say(f"[失败] {exc}")
            messagebox.showerror("发送失败", str(exc))
            return
        if ok:
            self._say("[成功] 测试消息已发出，请看一眼手机微信。")
        else:
            self._say("[失败] 平台拒绝了这次推送，请核对 Token 是否正确、是否已实名。")

    def on_run(self) -> None:
        ok, err = self._collect()
        if not ok:
            messagebox.showwarning("还没填完", err)
            return
        self._say("正在运行一次完整流程…")
        self.root.update_idletasks()
        try:
            proc = subprocess.run(
                [str(PY), "run_once.py", "--all"],
                cwd=str(ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=300,
            )
        except Exception as exc:  # noqa: BLE001
            self._say(f"[失败] {exc}")
            return
        tail = (proc.stdout or "").strip().splitlines()[-14:]
        self._say("\n".join(tail) if tail else "（无输出）")
        if proc.returncode == 0:
            self._say("[完成] 已生成简报，正在打开…")
            self.on_open_brief()
        else:
            self._say(f"[未完全成功] 退出码 {proc.returncode}，详见上方输出。")

    def on_open_brief(self) -> None:
        out = ROOT / "out"
        files = sorted(out.glob("brief_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            messagebox.showinfo("还没有简报", "先点「立即运行一次」。")
            return
        os.startfile(str(files[0]))  # noqa: S606

    def on_schedule(self) -> None:
        bat = ROOT / "每日推送.bat"
        if not bat.exists():
            messagebox.showerror("缺文件", "找不到 每日推送.bat，请重新解压项目。")
            return
        try:
            subprocess.run(
                ["schtasks", "/create", "/tn", TASK_NAME, "/tr", str(bat),
                 "/sc", "DAILY", "/st", "09:00", "/f"],
                capture_output=True, text=True, timeout=60,
            )
        except FileNotFoundError:
            messagebox.showerror("系统不支持", "找不到 schtasks，请手动设置计划任务。")
            return
        self._install_wrapper(bat)
        self._say("[已设置] 每天 9:00 自动运行（任务名：招投标工作台-每日9点）")
        self._say("提示：电脑需开机且不休眠；关机当天不会推送。")

    def _install_wrapper(self, bat: Path) -> None:
        """把任务目标再指向 bat 一次，确保工作目录正确。"""
        try:
            subprocess.run(
                ["schtasks", "/create", "/tn", TASK_NAME, "/tr", f'"{bat}"',
                 "/sc", "DAILY", "/st", "09:00", "/f"],
                capture_output=True, text=True, timeout=60,
            )
        except Exception:  # noqa: BLE001 - 已在上一步报告过
            pass

    def on_unschedule(self) -> None:
        try:
            subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
                           capture_output=True, text=True, timeout=60)
        except Exception as exc:  # noqa: BLE001
            self._say(f"[失败] {exc}")
            return
        self._say("[已取消] 每天自动运行已移除。")


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
