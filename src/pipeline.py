"""主流程编排（只读 MVP）。

fetch -> dedup/upsert -> match -> LLM 摘要 -> brief(MD+HTML) -> push(企微) 
全程只做本地写入（SQLite/文件）与内部通知，无任何报名/提交等对外写入动作。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .adapters.base import DataSourceAdapter
from .brief import render_html, render_markdown
from .config import ROOT
from .llm.factory import build_provider
from .matcher.scorer import score_notice
from .models import MatchResult
from .notifier.base import Notifier
from .storage.db import Database


class Pipeline:
    def __init__(self, cfg: dict, adapter: DataSourceAdapter, db: Database,
                 notifier: Notifier | None = None):
        self.cfg = cfg
        self.adapter = adapter
        self.db = db
        self.notifier = notifier
        self.llm = build_provider(cfg.get("llm", {}), db=db)

    def _now(self) -> datetime:
        """按配置时区取当前时间（默认东八区），避免本机时区与 UTC 混用导致跨天错位。"""
        tz_name = (self.cfg.get("app") or {}).get("timezone", "Asia/Shanghai")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = None
        return datetime.now(tz) if tz else datetime.now()

    def run(self, include_unchanged: bool = False) -> dict:
        """跑一次完整流程。

        include_unchanged=False：只处理新增/更新的公告（每日增量简报，默认）；
        include_unchanged=True：连内容未变化的也一并展示（当前全部可投项目，用于看板/复盘）。
        """
        run_id = self._now().strftime("%Y%m%d%H%M%S")
        self.db.audit("fetch", f"开始采集（数据源：{self.adapter.name}）", ref_id=run_id)

        try:
            notices = self.adapter.fetch()
        except Exception as exc:
            self.db.audit("fetch", f"采集失败：{exc}", ref_id=run_id, level="ERROR")
            raise
        self.db.audit("fetch", f"采集完成，共 {len(notices)} 条公告", ref_id=run_id,
                      detail={"count": len(notices), "source": self.adapter.name})

        results: list[MatchResult] = []
        items_for_brief: list[tuple[int, int, str]] = []

        for notice in notices:
            # 增量与去重：同一公告只保留一条记录
            pk, change = self.db.upsert_notice(notice)
            self.db.audit("fetch", f"公告入库：{notice.notice_id}（{change}）",
                          ref_id=notice.notice_id,
                          detail={"source_url": notice.source_url, "fetched_at": notice.fetched_at.isoformat()})
            if change == "unchanged" and not include_unchanged:
                # 内容未变化的旧公告不重复推送；--all 模式下仍纳入展示
                continue

            result = score_notice(notice, self.cfg)
            result.change_type = change
            result.summary = self.llm.summarize(result)
            self.db.save_match(pk, result)
            self.db.audit(
                "match",
                f"匹配完成：{notice.notice_id} 得分 {result.score}，推荐={result.recommended}",
                ref_id=notice.notice_id,
                detail={"score": result.score, "reasons": result.reasons, "risks": result.risks},
            )
            results.append(result)
            if result.recommended:
                items_for_brief.append((pk, result.score, change))

        # 简报只针对本轮新增/更新且推荐的项目；历史已推过的 unchanged 不重复出现
        run_date = self._now().strftime("%Y-%m-%d")
        owner = self.cfg.get("owner_email", "")
        md = render_markdown(results, run_date, owner)
        html = render_html(results, run_date, owner)

        out_dir = Path(self.cfg["app"]["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"brief_{run_id}.md"
        html_path = out_dir / f"brief_{run_id}.html"
        md_path.write_text(md, encoding="utf-8")
        html_path.write_text(html, encoding="utf-8")

        self.db.save_brief(run_date, md, html, str(md_path), str(html_path), items_for_brief)
        self.db.audit("brief", f"简报生成：{md_path.name} / {html_path.name}",
                      ref_id=run_id, detail={"count": len(items_for_brief)})

        pushed = False
        if self.notifier and self.cfg.get("notifier", {}).get("enabled", False):
            try:
                pushed = bool(self.notifier.send(f"招投标机会日报 {run_date}", md))
                self.db.audit("push", f"简报推送{'成功' if pushed else '未发送'}", ref_id=run_id)
            except Exception as exc:
                # 推送失败不影响已生成的简报，留痕后继续返回结果
                self.db.audit("push", f"简报推送失败：{exc}", ref_id=run_id, level="ERROR")
        else:
            self.db.audit("push", "通知器未启用，仅生成简报文件", ref_id=run_id)

        return {
            "run_id": run_id,
            "fetched": len(notices),
            "new_or_updated": len(results),
            "recommended": len(items_for_brief),
            "markdown": str(md_path),
            "html": str(html_path),
            "pushed": pushed,
        }

    def verify_manual_confirm(self, action: str, operator: str, approved: bool) -> None:
        """人工二次确认留痕入口（本阶段不触发任何对外动作，仅记录）。"""
        self.db.audit("manual_confirm", f"人工确认：{action} = {'通过' if approved else '拒绝'}",
                      ref_id=action, detail={"operator": operator, "approved": approved})
