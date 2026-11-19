-- SQLite 数据表结构（初始迁移，见 migrations/001_init.sql）
-- 合规：notices 保留 source_url / fetched_at / raw_snapshot；audit_logs 全程留痕。

CREATE TABLE IF NOT EXISTS notices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_id           TEXT    NOT NULL,          -- 源站公告 ID
    source              TEXT    NOT NULL,          -- 数据源标识
    identity_hash       TEXT    NOT NULL,          -- 去重键：hash(source + notice_id 或 url)
    content_hash        TEXT    NOT NULL,          -- 内容指纹，用于判定新增/更新
    title               TEXT,
    purchaser           TEXT,
    region              TEXT,
    budget_amount       REAL,
    registration_deadline TEXT,
    bid_open_time       TEXT,
    qualification       TEXT,
    source_url          TEXT    NOT NULL,          -- 原文链接
    publish_time        TEXT,
    fetched_at          TEXT    NOT NULL,          -- 抓取时间
    raw_snapshot        TEXT    NOT NULL DEFAULT '{}',  -- 原文快照（JSON）
    change_type         TEXT    NOT NULL DEFAULT 'new', -- new / updated
    first_seen_at       TEXT    NOT NULL,
    last_seen_at        TEXT    NOT NULL,
    UNIQUE(source, identity_hash)
);

CREATE INDEX IF NOT EXISTS idx_notices_identity ON notices(identity_hash);

CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_pk       INTEGER NOT NULL REFERENCES notices(id),
    score           INTEGER NOT NULL,
    dimensions_json TEXT    NOT NULL,
    reasons_json    TEXT    NOT NULL,
    risks_json      TEXT    NOT NULL,
    summary         TEXT,
    recommended     INTEGER NOT NULL,
    computed_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS briefs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date    TEXT    NOT NULL,
    markdown    TEXT    NOT NULL,
    html        TEXT    NOT NULL,
    md_path     TEXT,
    html_path   TEXT,
    item_count  INTEGER NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS brief_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id    INTEGER NOT NULL REFERENCES briefs(id),
    notice_pk   INTEGER NOT NULL REFERENCES notices(id),
    score       INTEGER NOT NULL,
    change_type TEXT    NOT NULL
);

-- 全程留痕：采集日志 / 匹配理由 / 人工确认记录 / 推送结果
CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    event       TEXT    NOT NULL,   -- fetch / match / brief / push / manual_confirm
    level       TEXT    NOT NULL DEFAULT 'INFO',
    ref_id      TEXT,               -- 关联的 notice identity_hash 或 run_id
    message     TEXT    NOT NULL,
    detail_json TEXT    NOT NULL DEFAULT '{}'
);
