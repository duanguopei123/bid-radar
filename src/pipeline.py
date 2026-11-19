"""主流程编排（只读 MVP）。

fetch -> dedup/upsert -> match -> LLM 摘要 -> brief(MD+HTML) -> push(企微) 
全程只做本地写入（SQLite/文件）与内部通知，无任何报名/提交等对外写入动作。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .adapters.base import DataSourceAdapter
from .brief import render_html, render_markdown
from .llm.factory import build_provider
from .matcher.scorer import score_notice
from .models import MatchResult, Notice
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
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"无效的时区配置：{tz_name}") from exc
        return datetime.now(tz)

    @staticmethod
    def _notice_from_row(row, fallback_time: datetime) -> Notice:
        """把数据库中的公告行还原为 Notice，供失败任务重试。"""
        def parse_date(value):
            return date.fromisoformat(value) if value else None

        def parse_datetime(value):
            return datetime.fromisoformat(value) if value else None

        snapshot = json.loads(row["raw_snapshot"] or "{}")
        if not isinstance(snapshot, dict):
            snapshot = {"value": snapshot}
        return Notice(
            notice_id=row["notice_id"],
            title=row["title"] or "",
            purchaser=row["purchaser"] or "",
            region=row["region"] or "",
            budget_amount=row["budget_amount"],
            registration_deadline=parse_date(row["registration_deadline"]),
            bid_open_time=parse_datetime(row["bid_open_time"]),
            qualification=row["qualification"] or "",
            source_url=row["source_url"] or "",
            publish_time=parse_date(row["publish_time"]) or fallback_time.date(),
            source=row["source"] or "unknown",
            fetched_at=parse_datetime(row["fetched_at"]) or fallback_time,
            raw_snapshot=snapshot,
        )

    def run(self, include_unchanged: bool = False) -> dict:
        """跑一次完整流程。

        include_unchanged=False：只处理新增/更新的公告（每日增量简报，默认）；
        include_unchanged=True：连内容未变化的也一并展示（当前全部可投项目，用于看板/复盘）。
        """
        now = self._now()
        business_date = now.date()
        run_id = now.strftime("%Y%m%d%H%M%S")
        self.db.audit("fetch", f"开始采集（数据源：{self.adapter.name}）", ref_id=run_id)

        try:
            notices = self.adapter.fetch()
        except Exception as exc:
            self.db.audit("fetch", f"采集失败：{exc}", ref_id=run_id, level="ERROR")
            raise
        self.db.audit("fetch", f"采集完成，共 {len(notices)} 条公告", ref_id=run_id,
                      detail={"count": len(notices), "source": self.adapter.name})

        work: dict[int, tuple[Notice, str]] = {}
        for notice in notices:
            pk, change = self.db.upsert_notice(notice)
            self.db.audit("fetch", f"公告入库：{notice.notice_id}（{change}）",
                          ref_id=notice.notice_id,
                          detail={"source_url": notice.source_url, "fetched_at": notice.fetched_at.isoformat()})
            if change != "unchanged" or include_unchanged:
                work[pk] = (notice, change)

        failed = 0
        for row in self.db.list_notices_needing_processing():
            pk = int(row["id"])
            if pk in work:
                continue
            try:
                work[pk] = (
                    self._notice_from_row(row, now),
                    row["change_type"] or "updated",
                )
            except Exception as exc:  # noqa: BLE001 - 单条公告失败不能阻断批次
                failed += 1
                self.db.mark_notice_processing_failed(pk, row["content_hash"], str(exc))
                self.db.audit(
                    "match",
                    f"待处理公告恢复失败：{row['notice_id']}：{exc}",
                    ref_id=row["notice_id"],
                    level="ERROR",
                )

        results: list[MatchResult] = []
        items_for_brief: list[tuple[int, int, str]] = []
        for pk, (notice, change) in sorted(work.items()):
            content_hash = notice.content_fingerprint
            try:
                self.db.mark_notice_processing_started(pk, content_hash)
                result = score_notice(
                    notice,
                    self.cfg,
                    business_date=business_date,
                )
                result.change_type = change
                result.summary = self.llm.summarize(result)
                self.db.save_match(pk, result)
                self.db.audit(
                    "match",
                    f"匹配完成：{notice.notice_id} 得分 {result.score}，推荐={result.recommended}",
                    ref_id=notice.notice_id,
                    detail={
                        "score": result.score,
                        "reasons": result.reasons,
                        "risks": result.risks,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - 记录后继续处理后续公告
                failed += 1
                self.db.mark_notice_processing_failed(pk, content_hash, str(exc))
                self.db.audit(
                    "match",
                    f"匹配失败：{notice.notice_id}：{exc}",
                    ref_id=notice.notice_id,
                    level="ERROR",
                )
                continue

            results.append(result)
            if result.recommended:
                items_for_brief.append((pk, result.score, change))

        run_date = business_date.isoformat()
        owner = self.cfg.get("owner_email", "")
        md = render_markdown(results, run_date, owner, business_date=business_date)
        html = render_html(results, run_date, owner, business_date=business_date)

        out_dir = Path(self.cfg["app"]["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"brief_{run_id}.md"
        html_path = out_dir / f"brief_{run_id}.html"
        md_path.write_text(md, encoding="utf-8")
        html_path.write_text(html, encoding="utf-8")

        brief_id = self.db.save_brief(
            run_date,
            md,
            html,
            str(md_path),
            str(html_path),
            items_for_brief,
        )
        self.db.audit("brief", f"简报生成：{md_path.name} / {html_path.name}",
                      ref_id=run_id, detail={"count": len(items_for_brief)})

        notifier_enabled = bool(
            self.notifier
            and self.cfg.get("notifier", {}).get("enabled", False)
            and getattr(self.notifier, "enabled", True)
        )
        if not notifier_enabled or not items_for_brief:
            self.db.mark_brief_delivery_skipped(
                brief_id,
                "通知器未启用" if not notifier_enabled else "本轮无推荐项目",
            )

        pushed = False
        delivery_status = "skipped"
        if notifier_enabled:
            attempted = 0
            delivery_failed = False
            for delivery in self.db.list_pending_brief_deliveries():
                pending_brief_id = int(delivery["id"])
                attempted += 1
                self.db.mark_brief_delivery_sending(pending_brief_id)
                try:
                    sent = bool(self.notifier.send(
                        f"招投标机会日报 {delivery['run_date']}",
                        delivery["markdown"],
                    ))
                except Exception as exc:  # noqa: BLE001 - 持久化为 failed 后续重试
                    delivery_failed = True
                    self.db.mark_brief_delivery_failed(pending_brief_id, str(exc))
                    self.db.audit(
                        "push",
                        f"简报推送失败：{exc}",
                        ref_id=str(delivery["run_date"]),
                        level="ERROR",
                    )
                    continue
                if sent:
                    self.db.mark_brief_delivery_sent(pending_brief_id)
                else:
                    delivery_failed = True
                    self.db.mark_brief_delivery_failed(
                        pending_brief_id,
                        "通知器返回失败",
                    )
                    self.db.audit(
                        "push",
                        "简报推送失败：通知器返回失败",
                        ref_id=str(delivery["run_date"]),
                        level="ERROR",
                    )
            if attempted:
                delivery_status = "failed" if delivery_failed else "sent"
                pushed = not delivery_failed
            self.db.audit(
                "push",
                f"投递完成：{delivery_status}",
                ref_id=run_id,
                detail={"attempted": attempted, "status": delivery_status},
                level="INFO" if delivery_status != "failed" else "ERROR",
            )
        else:
            self.db.audit("push", "通知器未启用，仅生成简报文件", ref_id=run_id)

        status = "failed" if failed or delivery_status == "failed" else "ok"
        return {
            "run_id": run_id,
            "fetched": len(notices),
            "new_or_updated": len(results),
            "failed": failed,
            "recommended": len(items_for_brief),
            "markdown": str(md_path),
            "html": str(html_path),
            "pushed": pushed,
            "delivery_status": delivery_status,
            "status": status,
        }

    def verify_manual_confirm(self, action: str, operator: str, approved: bool) -> None:
        """人工二次确认留痕入口（本阶段不触发任何对外动作，仅记录）。"""
        self.db.audit("manual_confirm", f"人工确认：{action} = {'通过' if approved else '拒绝'}",
                      ref_id=action, detail={"operator": operator, "approved": approved})
