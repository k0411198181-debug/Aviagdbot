 from typing import List, Optional
from config import MAX_HISTORY
from db_models import get_db


def upsert_user(uid: int, username: Optional[str], first_name: Optional[str] = None) -> None:
    c = get_db()
    c.execute(
        "INSERT INTO users(id,username,first_name) VALUES(?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
        (uid, username, first_name)
    )
    c.commit(); c.close()


def get_user(uid: int):
    c = get_db()
    r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    c.close(); return r


def is_onboarded(uid: int) -> bool:
    r = get_user(uid)
    return bool(r and r["onboarded"])


def set_onboarded(uid: int) -> None:
    c = get_db(); c.execute("UPDATE users SET onboarded=1 WHERE id=?", (uid,)); c.commit(); c.close()


def set_city(uid: int, iata: str) -> None:
    c = get_db(); c.execute("UPDATE users SET default_city=? WHERE id=?", (iata, uid)); c.commit(); c.close()


def set_currency(uid: int, cur: str) -> None:
    c = get_db(); c.execute("UPDATE users SET currency=? WHERE id=?", (cur, uid)); c.commit(); c.close()


def set_direct_only(uid: int, val: bool) -> None:
    c = get_db(); c.execute("UPDATE users SET direct_only=? WHERE id=?", (1 if val else 0, uid)); c.commit(); c.close()


def get_direct_only(uid: int) -> bool:
    r = get_user(uid)
    return bool(r and r["direct_only"])


def is_user_banned(uid: int) -> bool:
    c = get_db()
    r = c.execute("SELECT is_banned FROM users WHERE id=?", (uid,)).fetchone()
    c.close()
    return bool(r and r["is_banned"])


def ban_user(uid: int, banned: bool) -> None:
    c = get_db(); c.execute("UPDATE users SET is_banned=? WHERE id=?", (1 if banned else 0, uid)); c.commit(); c.close()


def get_user_plan(uid: int) -> str:
    c = get_db()
    r = c.execute("SELECT plan FROM users WHERE id=?", (uid,)).fetchone()
    c.close()
    return r["plan"] if r else "free"


def set_user_plan(uid: int, plan: str) -> None:
    c = get_db(); c.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid)); c.commit(); c.close()


def get_all_users_ids() -> List[int]:
    c = get_db()
    rows = c.execute("SELECT id FROM users WHERE is_banned=0").fetchall()
    c.close()
    return [r["id"] for r in rows]


def add_alert(uid: int, kind: str, origin: str, destination: str,
              month: str, threshold: int, return_month: str = "") -> int:
    c = get_db()
    cur = c.execute(
        "INSERT INTO alerts(user_id,kind,origin,destination,depart_month,return_month,threshold) "
        "VALUES(?,?,?,?,?,?,?)",
        (uid, kind, origin, destination, month, return_month, threshold)
    )
    aid = cur.lastrowid; c.commit(); c.close(); return aid


def get_user_alerts(uid: int):
    c = get_db()
    rows = c.execute("SELECT * FROM alerts WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
    c.close(); return rows


def get_active_alerts():
    c = get_db()
    rows = c.execute(
        "SELECT a.*, u.currency, u.direct_only "
        "FROM alerts a JOIN users u ON u.id=a.user_id "
        "WHERE a.is_active=1 AND u.is_banned=0"
    ).fetchall()
    c.close(); return rows


def remove_alert(uid: int, aid: int) -> bool:
    c = get_db(); c.execute("DELETE FROM alerts WHERE id=? AND user_id=?", (aid, uid))
    ok = c.execute("SELECT changes() AS n").fetchone()["n"] > 0; c.commit(); c.close(); return ok


def set_alert_active(aid: int, active: bool) -> None:
    c = get_db(); c.execute("UPDATE alerts SET is_active=? WHERE id=?", (1 if active else 0, aid)); c.commit(); c.close()


def update_alert_price(aid: int, price: int) -> None:
    c = get_db()
    c.execute("UPDATE alerts SET last_price=?, fired_count=fired_count+1 WHERE id=?", (price, aid))
    c.commit(); c.close()


def count_alerts(uid: int) -> int:
    c = get_db()
    r = c.execute("SELECT COUNT(*) AS n FROM alerts WHERE user_id=? AND is_active=1", (uid,)).fetchone()
    c.close(); return r["n"]


def is_seen(aid: int, key: str) -> bool:
    c = get_db()
    r = c.execute("SELECT 1 FROM seen_deals WHERE alert_id=? AND deal_key=?", (aid, key)).fetchone()
    c.close(); return r is not None


def mark_seen(aid: int, key: str) -> None:
    c = get_db()
    c.execute("INSERT OR IGNORE INTO seen_deals(alert_id,deal_key) VALUES(?,?)", (aid, key))
    c.commit(); c.close()


def cleanup_seen_deals(days: int = 30) -> None:
    c = get_db()
    c.execute("DELETE FROM seen_deals WHERE seen_at < datetime('now', ?)", (f"-{days} days",))
    c.commit(); c.close()


def add_history(uid: int, kind: str, origin: str, destination: str,
                query_param: str, min_price: Optional[int], currency: str) -> None:
    c = get_db()
    c.execute(
        "INSERT INTO search_history(user_id,kind,origin,destination,query_param,min_price,currency) "
        "VALUES(?,?,?,?,?,?,?)",
        (uid, kind, origin, destination, query_param, min_price, currency)
    )
    c.execute(
        "DELETE FROM search_history WHERE user_id=? AND id NOT IN "
        "(SELECT id FROM search_history WHERE user_id=? ORDER BY id DESC LIMIT ?)",
        (uid, uid, MAX_HISTORY)
    )
    c.commit(); c.close()


def get_history(uid: int, limit: int = 10):
    c = get_db()
    rows = c.execute(
        "SELECT * FROM search_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (uid, limit)
    ).fetchall()
    c.close(); return rows


def log_saving(uid: int, alert_id: int, origin: str, destination: str,
               threshold: int, found_price: int, currency: str) -> None:
    saved = threshold - found_price
    if saved <= 0:
        return
    c = get_db()
    c.execute(
        "INSERT INTO savings_log(user_id,alert_id,origin,destination,threshold,found_price,saved,currency) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (uid, alert_id, origin, destination, threshold, found_price, saved, currency)
    )
    c.commit(); c.close()


def get_savings_stats(uid: int) -> dict:
    c = get_db()
    row = c.execute(
        "SELECT COUNT(*) AS deals, SUM(saved) AS total_saved, MIN(found_price) AS best_price "
        "FROM savings_log WHERE user_id=?", (uid,)
    ).fetchone()
    searches     = c.execute("SELECT COUNT(*) AS n FROM search_history WHERE user_id=?", (uid,)).fetchone()
    alerts_fired = c.execute("SELECT SUM(fired_count) AS n FROM alerts WHERE user_id=?", (uid,)).fetchone()
    c.close()
    return {
        "deals":        int(row["deals"] or 0),
        "total_saved":  int(row["total_saved"] or 0),
        "best_price":   int(row["best_price"] or 0),
        "searches":     int(searches["n"] or 0),
        "alerts_fired": int(alerts_fired["n"] or 0),
    }


def log_event(uid: Optional[int], event_type: str, payload: str = "") -> None:
    try:
        c = get_db()
        c.execute(
            "INSERT INTO events(user_id,event_type,payload) VALUES(?,?,?)",
            (uid, event_type, payload)
        )
        c.commit(); c.close()
    except Exception:
        pass


def get_global_stats() -> dict:
    c = get_db()
    users   = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    alerts  = c.execute("SELECT COUNT(*) AS n FROM alerts WHERE is_active=1").fetchone()["n"]
    notifs  = c.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type='alert_triggered'"
    ).fetchone()["n"]
    c.close()
    return {"users": users, "active_alerts": alerts, "notifications_sent": notifs}   
