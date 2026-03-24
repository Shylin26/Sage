CREATE TABLE IF NOT EXISTS signals (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    TEXT DEFAULT '{}',
    urgency     REAL DEFAULT 0.5,
    urr_score   REAL DEFAULT 0.0,
    summary     TEXT DEFAULT '',
    received_at TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS briefings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL UNIQUE,
    narrative   TEXT NOT NULL,
    signals_used TEXT DEFAULT '[]',
    delivered   INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signal_feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   TEXT NOT NULL,
    acted_on    INTEGER DEFAULT 0,
    ignored     INTEGER DEFAULT 0,
    date        TEXT NOT NULL
);