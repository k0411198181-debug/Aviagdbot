"""
admin_handlers.py — команды администратора.

/makeadmin <secret>  — получить права (секрет из .env ADMIN_SECRET)
/admin               — панель с метриками
/ban <user_id>       — заблокировать пользователя
/unban <user_id>     — разблокировать
/setplan <id> <plan> — изменить тариф (free / pro)
/broadcast <текст>   — рассылка всем незабаненным

Доступ только через /makeadmin с секретом.
"""

import functools
import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from config import ADMIN_SECRET
from db.queries import (
    ban_user,
    get_all_users_ids,
    get_global_stats,
    get_user,
    get_user_plan,
    log_event,
    set_user_plan,
    upsert_user,
)

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    return get_user_plan(user_id) == "admin"


def _require_admin(func):
    @functools.wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        if not _is_admin(message.from_user.id):
            await message.answer("⛔ Недостаточно прав.")
            return
        return await func(message, *args, **kwargs)
    return wrapper


# ── /makeadmin <secret> ────────────────────────────────────────────────────

@router.message(Command("makeadmin"))
async def cmd_makeadmin(message: Message):
    upsert_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or parts[1].strip() != ADMIN_SECRET:
        await message.answer("❌ Неверный секрет.")
        logger.warning("Неудачная попытка /makeadmin user_id=%s", message.from_user.id)
        return
    set_user_plan(message.from_user.id, "admin")
    await message.answer("✅ Права администратора получены.")
    logger.info("Новый администратор: %s", message.from_user.id)


# ── /admin ─────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
@_require_admin
async def cmd_admin(message: Message):
    s = get_global_stats()
    await message.answer(
        "🛠 <b>Панель администратора</b>\n\n"
        f"👤 Пользователей: <b>{s['users']}</b>\n"
        f"🔔 Активных алертов: <b>{s['active_alerts']}</b>\n"
        f"📨 Уведомлений отправлено: <b>{s['notifications_sent']}</b>\n\n"
        "<b>Команды:</b>\n"
        "/ban &lt;id&gt;\n"
        "/unban &lt;id&gt;\n"
        "/setplan &lt;id&gt; &lt;free|pro&gt;\n"
        "/broadcast &lt;текст&gt;"
    )


# ── /ban / /unban ──────────────────────────────────────────────────────────

@router.message(Command("ban"))
@_require_admin
async def cmd_ban(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Использование: /ban &lt;user_id&gt;")
        return
    target = int(parts[1].strip())
    ban_user(target, True)
    await message.answer(f"🚫 Пользователь <code>{target}</code> заблокирован.")
    log_event(message.from_user.id, "ban", str(target))


@router.message(Command("unban"))
@_require_admin
async def cmd_unban(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("Использование: /unban &lt;user_id&gt;")
        return
    target = int(parts[1].strip())
    ban_user(target, False)
    await message.answer(f"✅ Пользователь <code>{target}</code> разблокирован.")
    log_event(message.from_user.id, "unban", str(target))


# ── /setplan ───────────────────────────────────────────────────────────────

@router.message(Command("setplan"))
@_require_admin
async def cmd_setplan(message: Message):
    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit() or parts[2] not in ("free", "pro", "admin"):
        await message.answer("Использование: /setplan &lt;user_id&gt; &lt;free|pro|admin&gt;")
        return
    target = int(parts[1])
    plan   = parts[2]
    if not get_user(target):
        await message.answer("❌ Пользователь не найден в БД.")
        return
    set_user_plan(target, plan)
    await message.answer(f"✅ Тариф <code>{target}</code> → <b>{plan}</b>")
    log_event(message.from_user.id, "setplan", f"{target}:{plan}")


# ── /broadcast ─────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
@_require_admin
async def cmd_broadcast(message: Message, bot: Bot):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Использование: /broadcast &lt;текст рассылки&gt;")
        return

    text   = parts[1].strip()
    ids    = get_all_users_ids()
    status = await message.answer(f"📤 Рассылка по {len(ids)} пользователям...")
    ok = failed = 0

    for uid in ids:
        try:
            await bot.send_message(chat_id=uid, text=text)
            ok += 1
        except Exception:
            failed += 1

    await status.edit_text(
        f"✅ Рассылка завершена.\n"
        f"Отправлено: <b>{ok}</b>  Ошибок: <b>{failed}</b>"
    )
    log_event(message.from_user.id, "broadcast", f"ok={ok} failed={failed}")
