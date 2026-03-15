import sqlite3
from config import DB_PATH


def get_db() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db() -> None:
    c = get_db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id           INTEGER PRIMARY KEY,
        username     TEXT,
        first_name   TEXT,
        default_city TEXT DEFAULT 'MOW',
        currency     TEXT DEFAULT 'rub',
        direct_only  INTEGER NOT NULL DEFAULT 0,
        onboarded    INTEGER NOT NULL DEFAULT 0,
        plan         TEXT NOT NULL DEFAULT 'free',
        is_banned    INTEGER NOT NULL DEFAULT 0,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS alerts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind         TEXT NOT NULL DEFAULT 'avia',
        origin       TEXT NOT NULL,
        destination  TEXT NOT NULL,
        depart_month TEXT NOT NULL,
        return_month TEXT DEFAULT '',
        threshold    INTEGER NOT NULL,
        is_active    INTEGER NOT NULL DEFAULT 1,
        last_price   INTEGER,
        fired_count  INTEGER NOT NULL DEFAULT 0,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS search_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind        TEXT NOT NULL DEFAULT 'avia',
        origin      TEXT NOT NULL,
        destination TEXT NOT NULL,
        query_param TEXT,
        min_price   INTEGER,
        currency    TEXT DEFAULT 'rub',
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS savings_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        alert_id    INTEGER,
        origin      TEXT,
        destination TEXT,
        threshold   INTEGER NOT NULL,
        found_price INTEGER NOT NULL,
        saved       INTEGER NOT NULL,
        currency    TEXT DEFAULT 'rub',
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS seen_deals (
        alert_id  INTEGER NOT NULL,
        deal_key  TEXT NOT NULL,
        seen_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(alert_id, deal_key)
    );

    CREATE TABLE IF NOT EXISTS events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER,
        event_type  TEXT NOT NULL,
        payload     TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_alerts_active  ON alerts(is_active);
    CREATE INDEX IF NOT EXISTS idx_history_user   ON search_history(user_id);
    CREATE INDEX IF NOT EXISTS idx_savings_user   ON savings_log(user_id);
    CREATE INDEX IF NOT EXISTS idx_events_type    ON events(event_type);
    """)
    c.commit()

    # ── Миграция для существующих БД (ALTER TABLE безопасен при повторе) ──
    migrations = [
        "ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'free'",
        "ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE alerts ADD COLUMN return_month TEXT DEFAULT ''",
        "ALTER TABLE seen_deals ADD COLUMN seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]
    for sql in migrations:
        try:
            c.execute(sql)
            c.commit()
        except Exception:
            pass  # Колонка уже существует — OK

    c.close()
