"""monitor.py — фоновая проверка алертов + очистка seen_deals."""

import html
import logging

from aiogram import Bot
from db.queries import (
    cleanup_seen_deals,
    get_active_alerts,
    is_seen,
    log_event,
    log_saving,
    mark_seen,
    update_alert_price,
)
from services.aviasales import SYM, _link, get_min_price

logger = logging.getLogger(__name__)


async def check_all_alerts(bot: Bot) -> None:
    logger.info("Проверка алертов")
    rows  = get_active_alerts()
    fired = 0

    for row in rows:
        if row["kind"] != "avia":
            continue
        try:
            return_month = row["return_month"] if "return_month" in row.keys() else ""
            price = await get_min_price(
                row["origin"], row["destination"],
                row["depart_month"], row["currency"],
                return_month=return_month,
            )
            if not price or price > row["threshold"]:
                continue

            key = f"{row['origin']}-{row['destination']}-{row['depart_month']}-{price}"
            if is_seen(row["id"], key):
                continue

            sym   = SYM.get(row["currency"], "₽")
            saved = row["threshold"] - price
            link  = _link(row["origin"], row["destination"], row["depart_month"] + "-01")
            rt_str = f" ↔ {row['destination']}" if return_month else f" → {row['destination']}"

            text = (
                f"🚨 <b>Цена упала по твоему алерту!</b>\n\n"
                f"✈️ <b>{row['origin']}{rt_str}</b>\n"
                f"📅 {row['depart_month']}"
                + (f" / возврат {return_month}" if return_month else "") + "\n\n"
                f"💰 Цена: <b>{price:,} {sym}</b>\n"
                f"📉 Порог был: {row['threshold']:,} {sym}\n"
                f"🎉 Экономия: <b>{saved:,} {sym}</b>\n\n"
                f'🔗 <a href="{html.escape(link)}">Купить билет →</a>'
            )
            await bot.send_message(row["user_id"], text, disable_web_page_preview=True)
            mark_seen(row["id"], key)
            update_alert_price(row["id"], price)
            log_saving(
                row["user_id"], row["id"],
                row["origin"], row["destination"],
                row["threshold"], price, row["currency"],
            )
            log_event(row["user_id"], "alert_triggered",
                      f"alert_id={row['id']} price={price}")
            fired += 1
        except Exception as e:
            logger.exception("Ошибка alert_id=%s: %s", row["id"], e)

    logger.info("Алерты: отправлено %s", fired)

    # Чистим seen_deals старше 30 дней (чтобы таблица не росла бесконечно)
    try:
        cleanup_seen_deals(days=30)
    except Exception as e:
        logger.warning("cleanup_seen_deals: %s", e)
