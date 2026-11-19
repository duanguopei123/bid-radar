"""SQLite 存储层：建表、公告增量 upsert、匹配结果、简报与留痕日志。

合规：所有写入都是本地数据库写入（留痕），不涉及任何对外写操作。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..models import MatchResult, Notice

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        # 允许定时任务与手动运行并存，避免 database is locked
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.conn.commit()

    # ---------- 公告增量与去重 ----------
    def identity_hash(self, notice: Notice) -> str:
        """去重键：优先公告 ID，其次原文链接，最后退化为标题+采购人。

        避免 notice_id 与 source_url 同时为空时，所有公告撞进同一个键。
        """
        import hashlib
        key = notice.notice_id or notice.source_url or f"{notice.title}|{notice.purchaser}"
        return hashlib.sha256(f"{notice.source}:{key}".encode("utf-8")).hexdigest()

    def get_notice(self, identity_hash: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM notices WHERE identity_hash = ?", (identity_hash,)
        ).fetchone()

    def upsert_notice(self, notice: Notice) -> tuple[int, str]:
        """返回 (row_pk, change_type)。同一公告只更新内容指纹与最近抓取时间。"""
        ihash = self.identity_hash(notice)
        existing = self.get_notice(ihash)
        now = _now()
        fetched = _iso(notice.fetched_at)
        snapshot = json.dumps(notice.raw_snapshot, ensure_ascii=False, default=str)

        if existing is None:
            cur = self.conn.execute(
                """INSERT INTO notices
                   (notice_id, source, identity_hash, content_hash, title, purchaser, region,
                    budget_amount, registration_deadline, bid_open_time, qualification,
                    source_url, publish_time, fetched_at, raw_snapshot, change_type,
                    first_seen_at, last_seen_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    notice.notice_id, notice.source, ihash, notice.content_fingerprint,
                    notice.title, notice.purchaser, notice.region, notice.budget_amount,
                    _iso(notice.registration_deadline) if notice.registration_deadline else None,
                    _iso(notice.bid_open_time) if notice.bid_open_time else None,
                    notice.qualification, notice.source_url,
                    notice.publish_time.isoformat() if notice.publish_time else None,
                    fetched, snapshot, "new", now, now,
                ),
            )
            self.conn.commit()
            return int(cur.lastrowid), "new"

        change = "updated" if existing["content_hash"] != notice.content_fingerprint else "unchanged"
        if change == "updated":
            self.conn.execute(
                """UPDATE notices SET content_hash=?, title=?, purchaser=?, region=?,
                   budget_amount=?, registration_deadline=?, bid_open_time=?, qualification=?,
                   source_url=?, publish_time=?, fetched_at=?, raw_snapshot=?,
                   change_type='updated', last_seen_at=? WHERE id=?""",
                (
                    notice.content_fingerprint, notice.title, notice.purchaser, notice.region,
                    notice.budget_amount,
                    _iso(notice.registration_deadline) if notice.registration_deadline else None,
                    _iso(notice.bid_open_time) if notice.bid_open_time else None,
                    notice.qualification, notice.source_url,
                    notice.publish_time.isoformat() if notice.publish_time else None,
                    fetched, snapshot, now, existing["id"],
                ),
            )
        else:
            self.conn.execute(
                "UPDATE notices SET fetched_at=?, last_seen_at=? WHERE id=?",
                (fetched, now, existing["id"]),
            )
        self.conn.commit()
        return int(existing["id"]), change

    # ---------- 匹配结果 ----------
    def save_match(self, notice_pk: int, result: MatchResult) -> None:
        self.conn.execute(
            """INSERT INTO matches
               (notice_pk, score, dimensions_json, reasons_json, risks_json, summary, recommended, computed_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                notice_pk, result.score,
                json.dumps([d.__dict__ for d in result.dimensions], ensure_ascii=False),
                json.dumps(result.reasons, ensure_ascii=False),
                json.dumps(result.risks, ensure_ascii=False),
                result.summary, int(result.recommended), _now(),
            ),
        )
        self.conn.commit()

    # ---------- 简报 ----------
    def save_brief(self, run_date: str, markdown: str, html: str,
                   md_path: str, html_path: str,
                   items: Iterable[tuple[int, int, str]]) -> int:
        item_list = list(items)
        cur = self.conn.execute(
            """INSERT INTO briefs (run_date, markdown, html, md_path, html_path, item_count, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (run_date, markdown, html, md_path, html_path, len(item_list), _now()),
        )
        bid = int(cur.lastrowid)
        for notice_pk, score, change in item_list:
            self.conn.execute(
                "INSERT INTO brief_items (brief_id, notice_pk, score, change_type) VALUES (?,?,?,?)",
                (bid, notice_pk, score, change),
            )
        self.conn.commit()
        return bid

    # ---------- 留痕日志 ----------
    def audit(self, event: str, message: str, ref_id: str | None = None,
              detail: dict[str, Any] | None = None, level: str = "INFO") -> None:
        self.conn.execute(
            "INSERT INTO audit_logs (ts, event, level, ref_id, message, detail_json) VALUES (?,?,?,?,?,?)",
            (_now(), event, level, ref_id, message, json.dumps(detail or {}, ensure_ascii=False, default=str)),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
