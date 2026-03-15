from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup,
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✈️ Авиабилеты"),   KeyboardButton(text="🚂 ЖД билеты")],
            [KeyboardButton(text="📅 Календарь цен"), KeyboardButton(text="🔥 Горящие")],
            [KeyboardButton(text="🔔 Мои алерты"),    KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🏨 Отели и туры"),  KeyboardButton(text="⚙️ Настройки")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def skip_kb(label: str = "Пропустить") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"➡️ {label}")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def yes_no_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Да, только прямые"), KeyboardButton(text="🔀 Любые рейсы")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def onboard_city_kb() -> ReplyKeyboardMarkup:
    cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань"]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=c)] for c in cities] + [[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def currency_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="₽ RUB", callback_data="cur:rub"),
        InlineKeyboardButton(text="$ USD", callback_data="cur:usd"),
        InlineKeyboardButton(text="€ EUR", callback_data="cur:eur"),
    ]])


def alert_kb(alert_id: int, active: bool) -> InlineKeyboardMarkup:
    t = "⏸ Пауза" if active else "▶️ Возобновить"
    d = f"pause:{alert_id}" if active else f"resume:{alert_id}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t, callback_data=d),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{alert_id}"),
    ]])


def share_kb(bot_username: str) -> InlineKeyboardMarkup:
    link  = f"https://t.me/{bot_username}"
    share = f"https://t.me/share/url?url={link}&text=Нашёл дешёвые билеты через этого бота 🔥"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📤 Поделиться ботом", url=share),
        InlineKeyboardButton(text="🔗 Скопировать ссылку", callback_data="copy_link"),
    ]])


def buy_kb(link: str, label: str = "Купить билет →") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, url=link),
    ]])


def hotels_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏨 Открыть HotelCar Bot", url="https://t.me/HotelCar_bot"),
    ]])
