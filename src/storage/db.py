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
        # 旧数据库按是否已有匹配记录回填；已有匹配的历史公告不能再次入简报。
        now = _now()
        self.conn.execute(
            """INSERT OR IGNORE INTO notice_processing
               (notice_pk, content_hash, status, attempts, completed_at, updated_at)
               SELECT n.id,
                      n.content_hash,
                      CASE WHEN EXISTS (
                          SELECT 1 FROM matches m WHERE m.notice_pk = n.id
                      ) THEN 'matched' ELSE 'pending' END,
                      0,
                      CASE WHEN EXISTS (
                          SELECT 1 FROM matches m WHERE m.notice_pk = n.id
                      ) THEN ? ELSE NULL END,
                      ?
               FROM notices n""",
            (now, now),
        )
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
            notice_pk = int(cur.lastrowid)
            self._queue_notice_processing(notice_pk, notice.content_fingerprint)
            self.conn.commit()
            return notice_pk, "new"

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
            self._queue_notice_processing(int(existing["id"]), notice.content_fingerprint)
        else:
            self.conn.execute(
                "UPDATE notices SET fetched_at=?, last_seen_at=? WHERE id=?",
                (fetched, now, existing["id"]),
            )
            self._queue_notice_processing(int(existing["id"]), existing["content_hash"])
        self.conn.commit()
        return int(existing["id"]), change

    def _queue_notice_processing(self, notice_pk: int, content_hash: str) -> None:
        """为当前内容版本排队；内容变化时重置此前已完成状态。"""
        self.conn.execute(
            """INSERT INTO notice_processing
               (notice_pk, content_hash, status, attempts, updated_at)
               VALUES (?, ?, 'pending', 0, ?)
               ON CONFLICT(notice_pk) DO UPDATE SET
                   content_hash=CASE
                       WHEN notice_processing.content_hash = excluded.content_hash
                       THEN notice_processing.content_hash
                       ELSE excluded.content_hash
                   END,
                   status=CASE
                       WHEN notice_processing.content_hash = excluded.content_hash
                       THEN notice_processing.status
                       ELSE 'pending'
                   END,
                   attempts=CASE
                       WHEN notice_processing.content_hash = excluded.content_hash
                       THEN notice_processing.attempts
                       ELSE 0
                   END,
                   last_error=CASE
                       WHEN notice_processing.content_hash = excluded.content_hash
                       THEN notice_processing.last_error
                       ELSE NULL
                   END,
                   started_at=CASE
                       WHEN notice_processing.content_hash = excluded.content_hash
                       THEN notice_processing.started_at
                       ELSE NULL
                   END,
                   completed_at=CASE
                       WHEN notice_processing.content_hash = excluded.content_hash
                       THEN notice_processing.completed_at
                       ELSE NULL
                   END,
                   updated_at=excluded.updated_at""",
            (notice_pk, content_hash, _now()),
        )

    def list_notices_needing_processing(self) -> list[sqlite3.Row]:
        """返回当前内容版本仍为 pending/failed 的公告。"""
        return self.conn.execute(
            """SELECT n.*
               FROM notices n
               JOIN notice_processing p ON p.notice_pk = n.id
               WHERE p.content_hash = n.content_hash
                 AND p.status IN ('pending', 'failed')
               ORDER BY p.updated_at, n.id"""
        ).fetchall()

    def mark_notice_processing_started(self, notice_pk: int, content_hash: str) -> None:
        now = _now()
        self.conn.execute(
            """UPDATE notice_processing
               SET status='pending', attempts=attempts + 1,
                   started_at=?, updated_at=?
               WHERE notice_pk=? AND content_hash=?""",
            (now, now, notice_pk, content_hash),
        )
        self.conn.commit()

    def mark_notice_processing_matched(self, notice_pk: int, content_hash: str) -> None:
        now = _now()
        self.conn.execute(
            """UPDATE notice_processing
               SET status='matched', last_error=NULL, completed_at=?, updated_at=?
               WHERE notice_pk=? AND content_hash=?""",
            (now, now, notice_pk, content_hash),
        )
        self.conn.commit()

    def mark_notice_processing_failed(
        self,
        notice_pk: int,
        content_hash: str,
        error: str,
    ) -> None:
        self.conn.execute(
            """UPDATE notice_processing
               SET status='failed', last_error=?, updated_at=?
               WHERE notice_pk=? AND content_hash=?""",
            (error, _now(), notice_pk, content_hash),
        )
        self.conn.commit()

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
        self.mark_notice_processing_matched(
            notice_pk,
            result.notice.content_fingerprint,
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
        self._ensure_brief_delivery(bid)
        self.conn.commit()
        return bid

    def _ensure_brief_delivery(self, brief_id: int) -> None:
        now = _now()
        self.conn.execute(
            """INSERT OR IGNORE INTO brief_deliveries
               (brief_id, status, attempts, queued_at, updated_at)
               VALUES (?, 'pending', 0, ?, ?)""",
            (brief_id, now, now),
        )

    def list_pending_brief_deliveries(self) -> list[sqlite3.Row]:
        """返回待发送或上次发送失败的简报。"""
        return self.conn.execute(
            """SELECT b.*, d.status AS delivery_status, d.attempts AS delivery_attempts,
                      d.last_error AS delivery_error
               FROM brief_deliveries d
               JOIN briefs b ON b.id = d.brief_id
               WHERE d.status IN ('pending', 'failed')
               ORDER BY d.updated_at, b.id"""
        ).fetchall()

    def mark_brief_delivery_sending(self, brief_id: int) -> None:
        now = _now()
        self.conn.execute(
            """UPDATE brief_deliveries
               SET status='sending', attempts=attempts + 1,
                   last_attempt_at=?, updated_at=?
               WHERE brief_id=?""",
            (now, now, brief_id),
        )
        self.conn.commit()

    def mark_brief_delivery_sent(self, brief_id: int) -> None:
        now = _now()
        self.conn.execute(
            """UPDATE brief_deliveries
               SET status='sent', last_error=NULL, sent_at=?, updated_at=?
               WHERE brief_id=?""",
            (now, now, brief_id),
        )
        self.conn.commit()

    def mark_brief_delivery_failed(self, brief_id: int, error: str) -> None:
        self.conn.execute(
            """UPDATE brief_deliveries
               SET status='failed', last_error=?, updated_at=?
               WHERE brief_id=?""",
            (error, _now(), brief_id),
        )
        self.conn.commit()

    def mark_brief_delivery_skipped(self, brief_id: int, reason: str = "") -> None:
        self.conn.execute(
            """UPDATE brief_deliveries
               SET status='skipped', last_error=?, updated_at=?
               WHERE brief_id=?""",
            (reason or None, _now(), brief_id),
        )
        self.conn.commit()

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
