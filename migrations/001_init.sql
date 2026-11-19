-- 迁移 001：初始建表（与 src/storage/schema.sql 保持一致）
-- 执行方式：程序启动时自动执行；也可手动：sqlite3 data/bidding.db < migrations/001_init.sql
CREATE TABLE IF NOT EXISTS notices (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    notice_id           TEXT    NOT NULL,
    source              TEXT    NOT NULL,
    identity_hash       TEXT    NOT NULL,
    content_hash        TEXT    NOT NULL,
    title               TEXT,
    purchaser           TEXT,
    region              TEXT,
    budget_amount       REAL,
    registration_deadline TEXT,
    bid_open_time       TEXT,
    qualification       TEXT,
    source_url          TEXT    NOT NULL,
    publish_time        TEXT,
    fetched_at          TEXT    NOT NULL,
    raw_snapshot        TEXT    NOT NULL DEFAULT '{}',
    change_type         TEXT    NOT NULL DEFAULT 'new',
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

CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    event       TEXT    NOT NULL,
    level       TEXT    NOT NULL DEFAULT 'INFO',
    ref_id      TEXT,
    message     TEXT    NOT NULL,
    detail_json TEXT    NOT NULL DEFAULT '{}'
);
