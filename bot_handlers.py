"""
handlers.py — все хэндлеры бота.

Фичи: онбординг, авиа (туда / туда-обратно), ЖД, календарь,
      горящие + error fares, алерты с возвратом, история,
      статистика, поделиться, фильтр прямых, тарифы free/pro.

Исправления vs предыдущей версии:
  - Имя города при нажатии «Пропустить» показывается корректно
  - MAX_HISTORY берётся из config, а не хардкодится
  - Валидация даты ЖД: нельзя выбрать прошедшую дату
  - Мёртвый код cb_currency / Onboarding.currency убран
"""

import html
import logging
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.fsm import (
    AddAlert, CalendarSearch, Onboarding,
    SearchAvia, SearchTrain, SetCity,
)
from bot.keyboards import (
    alert_kb, cancel_kb, currency_inline, main_menu,
    onboard_city_kb, share_kb, skip_kb, yes_no_kb,
)
from config import BOT_USERNAME, MAX_ALERTS_FREE, MAX_ALERTS_PRO
from db.queries import (
    add_alert, add_history, count_alerts, get_direct_only,
    get_history, get_savings_stats, get_user, get_user_alerts,
    get_user_plan, is_onboarded, is_user_banned, log_event,
    remove_alert, set_alert_active, set_city, set_currency,
    set_direct_only, set_onboarded, update_alert_price, upsert_user,
)
from services.aviasales import (
    SYM, _link, get_month_calendar, get_special_offers,
    search_cheapest, search_latest,
)
from services.iata import resolve_iata, resolve_iata_async, resolve_train_station
from services.tutu import get_popular_routes, get_train_link

logger = logging.getLogger(__name__)
router = Router()


# ── Хелперы ───────────────────────────────────────────────────────────────

def _valid_month(s: str) -> bool:
    try:
        datetime.strptime(s.strip() + "-01", "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _valid_date(s: str) -> bool:
    try:
        d = datetime.strptime(s.strip(), "%Y-%m-%d")
        return d.date() >= datetime.now().date()   # FIX: нельзя выбирать прошлое
    except ValueError:
        return False


async def _reg(m: Message) -> bool:
    """Регистрирует пользователя и проверяет бан. Возвращает False если забанен."""
    upsert_user(m.from_user.id, m.from_user.username, m.from_user.first_name)
    if is_user_banned(m.from_user.id):
        await m.answer("🚫 Ваш аккаунт заблокирован.")
        return False
    return True


def _city_from_user(row) -> str:
    return row["default_city"] if row and "default_city" in row.keys() else "MOW"


def _currency_from_user(row) -> str:
    return row["currency"] if row and "currency" in row.keys() else "rub"


def _city_name(iata: str) -> str:
    """FIX: получаем читаемое имя города из IATA-кода."""
    res = resolve_iata(iata)
    return res[1] if res else iata


def _fmt_avia(tickets, origin: str, dest: str, sym: str, label: str,
              direct_only: bool, return_month: str = "") -> str:
    filt = "  ·  только прямые" if direct_only else ""
    rt_label = f" ↔ {dest} (туда-обратно)" if return_month else f" → {dest}"
    if not tickets:
        return (
            f"😔 По маршруту <b>{origin}{rt_label}</b> {label} данных нет{filt}.\n"
            "Попробуй другой месяц или сними фильтр прямых в /settings"
        )
    lines = [f"✈️ <b>{origin}{rt_label}</b>  {label}{filt}\n"]
    for i, t in enumerate(tickets[:6], 1):
        tr = "🟢 прямой" if t.transfers == 0 else f"🔁 {t.transfers} пересадки"
        ret_str = f"  ↩ {t.return_date}" if t.return_date else ""
        lines.append(
            f"{i}. <b>{t.depart_date}</b>{ret_str}  💰 <b>{t.price:,} {sym}</b>  {tr}\n"
            f"   🔗 <a href=\"{html.escape(t.link)}\">Купить</a>\n"
        )
    return "\n".join(lines)


# ── ОНБОРДИНГ ─────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not await _reg(message):
        return
    await state.clear()
    log_event(message.from_user.id, "start")

    if not is_onboarded(message.from_user.id):
        await state.set_state(Onboarding.city)
        await message.answer(
            "👋 Привет! Я <b>TicketRadar</b> — ищу дешёвые авиабилеты и ЖД.\n\n"
            "Давай настроим бота за 3 шага — это займёт 30 секунд.\n\n"
            "<b>Шаг 1/3.</b> Из какого города обычно летишь?\n"
            "Выбери или напиши сам:",
            reply_markup=onboard_city_kb(),
        )
        return

    row  = get_user(message.from_user.id)
    city = _city_from_user(row)
    plan = get_user_plan(message.from_user.id)
    s    = get_savings_stats(message.from_user.id)
    saved_str = f"  💰 Сэкономил: <b>{s['total_saved']:,} ₽</b>" if s["total_saved"] else ""

    await message.answer(
        f"✈️🚂 <b>TicketRadar</b>\n\n"
        f"🏙 Город: <b>{_city_name(city)}</b>  "
        f"⭐ Тариф: <b>{plan}</b>{saved_str}\n\n"
        f"Используй кнопки меню 👇",
        reply_markup=main_menu(),
    )


@router.message(Onboarding.city, F.text != "❌ Отмена")
async def onboard_city(message: Message, state: FSMContext):
    result = await resolve_iata_async(message.text.strip())
    if not result:
        await message.answer("❌ Город не найден. Выбери из списка или напиши IATA (MOW, LED, AER).")
        return
    iata, name = result
    set_city(message.from_user.id, iata)
    await state.set_state(Onboarding.currency)
    await message.answer(
        f"✅ Город: <b>{name}</b>\n\n"
        f"<b>Шаг 2/3.</b> В какой валюте показывать цены?",
        reply_markup=currency_inline(),
    )


@router.callback_query(Onboarding.currency, F.data.startswith("cur:"))
async def onboard_currency(callback: CallbackQuery, state: FSMContext):
    cur = callback.data.split(":")[1]
    set_currency(callback.from_user.id, cur)
    await callback.message.edit_text(f"✅ Валюта: <b>{cur.upper()}</b>")
    await state.set_state(Onboarding.direct)
    await callback.message.answer(
        "<b>Шаг 3/3.</b> Фильтр прямых рейсов?\n\n"
        "🟢 <b>Только прямые</b> — без пересадок, быстрее\n"
        "🔀 <b>Любые рейсы</b> — включая с пересадками, больше вариантов",
        reply_markup=yes_no_kb(),
    )
    await callback.answer()


@router.message(Onboarding.direct)
async def onboard_direct(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    direct = message.text.startswith("✅")
    set_direct_only(message.from_user.id, direct)
    set_onboarded(message.from_user.id)
    await state.clear()
    row   = get_user(message.from_user.id)
    city  = _city_from_user(row)
    filt  = "только прямые" if direct else "все рейсы"
    await message.answer(
        f"🎉 <b>Всё готово!</b>\n\n"
        f"🏙 Город: <b>{_city_name(city)}</b>\n"
        f"💱 Валюта: <b>{_currency_from_user(row).upper()}</b>\n"
        f"✈️ Фильтр: <b>{filt}</b>\n\n"
        f"Теперь можешь искать билеты 👇\n"
        f"Настройки можно изменить через /settings",
        reply_markup=main_menu(),
    )


# ── АВИАБИЛЕТЫ (с возвратом) ───────────────────────────────────────────────

@router.message(Command("search"))
@router.message(F.text == "✈️ Авиабилеты")
async def cmd_avia(message: Message, state: FSMContext):
    if not await _reg(message):
        return
    row  = get_user(message.from_user.id)
    city = _city_from_user(row)
    await state.set_state(SearchAvia.origin)
    await state.update_data(default_city=city)
    await message.answer(
        "✈️ <b>Поиск авиабилетов</b>\n\n"
        f"Шаг 1/4. Откуда?\n"
        f"Город по умолч.: <b>{_city_name(city)}</b>",
        reply_markup=skip_kb(_city_name(city)),  # FIX: показываем имя, а не код
    )


@router.message(SearchAvia.origin)
async def fsm_avia_origin(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    data = await state.get_data()
    if message.text.startswith("➡️"):
        iata = data["default_city"]
        name = _city_name(iata)   # FIX: правильное имя вместо IATA-кода
    else:
        result = await resolve_iata_async(message.text.strip())
        if not result:
            await message.answer("❌ Город не найден. Напиши название или IATA-код.")
            return
        iata, name = result
    await state.update_data(origin=iata, origin_name=name)
    await state.set_state(SearchAvia.destination)
    await message.answer(f"✅ Откуда: <b>{name}</b>\n\nШаг 2/4. Куда?", reply_markup=cancel_kb())


@router.message(SearchAvia.destination)
async def fsm_avia_dest(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    result = await resolve_iata_async(message.text.strip())
    if not result:
        await message.answer("❌ Город не найден.")
        return
    iata, name = result
    await state.update_data(destination=iata, dest_name=name)
    await state.set_state(SearchAvia.month)
    nxt = (datetime.now() + timedelta(days=30)).strftime("%Y-%m")
    await message.answer(
        f"✅ Куда: <b>{name}</b>\n\n"
        f"Шаг 3/4. Месяц вылета (<code>YYYY-MM</code>):\n"
        f"Например: <code>{nxt}</code>",
        reply_markup=cancel_kb(),
    )


@router.message(SearchAvia.month)
async def fsm_avia_month(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    month = message.text.strip()
    if not _valid_month(month):
        await message.answer("❌ Формат: <code>2025-09</code>")
        return
    await state.update_data(month=month)
    await state.set_state(SearchAvia.return_month)
    await message.answer(
        f"✅ Вылет: <b>{month}</b>\n\n"
        f"Шаг 4/4. Месяц обратного рейса (или пропусти — только туда):",
        reply_markup=skip_kb("Только туда"),
    )


@router.message(SearchAvia.return_month)
async def fsm_avia_return(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    data = await state.get_data()
    return_month = ""
    if not message.text.startswith("➡️"):
        rm = message.text.strip()
        if not _valid_month(rm):
            await message.answer("❌ Формат: <code>2025-10</code>, или нажми «➡️ Только туда».")
            return
        return_month = rm
    await state.clear()

    row      = get_user(message.from_user.id)
    currency = _currency_from_user(row)
    direct   = get_direct_only(message.from_user.id)
    sym      = SYM.get(currency, "₽")
    label    = f"{data['month']}" + (f" ↔ {return_month}" if return_month else "")

    wait = await message.answer(
        f"🔍 Ищу {data['origin_name']} → {data['dest_name']} на {label}...",
        reply_markup=main_menu(),
    )

    tickets = []; err = ""
    try:
        tickets = await search_cheapest(
            data["origin"], data["destination"], data["month"],
            currency, direct, return_month=return_month,
        )
    except Exception as e:
        logger.error("search_cheapest: %s", e)
        err = "⚠️ Данные по месяцу недоступны. "

    if not tickets:
        try:
            tickets = await search_latest(data["origin"], data["destination"], currency, 8, direct)
            if err:
                err += "Показываю из кэша 48ч."
        except Exception as e:
            logger.error("search_latest: %s", e)

    min_price = min((t.price for t in tickets), default=None)
    add_history(message.from_user.id, "avia", data["origin"], data["destination"],
                label, min_price, currency)
    log_event(message.from_user.id, "search_avia", f"{data['origin']}-{data['destination']}-{label}")

    text = _fmt_avia(tickets, data["origin_name"], data["dest_name"], sym, label, direct, return_month)
    if err:
        text = err + "\n\n" + text
    await wait.edit_text(text, disable_web_page_preview=True)


# ── КАЛЕНДАРЬ ЦЕН ─────────────────────────────────────────────────────────

@router.message(Command("calendar"))
@router.message(F.text == "📅 Календарь цен")
async def cmd_calendar(message: Message, state: FSMContext):
    if not await _reg(message):
        return
    row  = get_user(message.from_user.id)
    city = _city_from_user(row)
    await state.set_state(CalendarSearch.origin)
    await state.update_data(default_city=city)
    await message.answer(
        "📅 <b>Календарь дешёвых дней</b>\n\n"
        "Покажу на каждый день — когда лететь дешевле всего.\n\n"
        f"Шаг 1/2. Откуда?\n"
        f"Город по умолч.: <b>{_city_name(city)}</b>",
        reply_markup=skip_kb(_city_name(city)),
    )


@router.message(CalendarSearch.origin)
async def fsm_cal_origin(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    data = await state.get_data()
    if message.text.startswith("➡️"):
        iata = data["default_city"]
        name = _city_name(iata)
    else:
        result = await resolve_iata_async(message.text.strip())
        if not result:
            await message.answer("❌ Город не найден.")
            return
        iata, name = result
    await state.update_data(origin=iata, origin_name=name)
    await state.set_state(CalendarSearch.destination)
    await message.answer(f"✅ Откуда: <b>{name}</b>\n\nШаг 2/2. Куда?", reply_markup=cancel_kb())


@router.message(CalendarSearch.destination)
async def fsm_cal_dest(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    result = await resolve_iata_async(message.text.strip())
    if not result:
        await message.answer("❌ Город не найден.")
        return
    iata, name = result
    data     = await state.get_data()
    await state.clear()

    row      = get_user(message.from_user.id)
    currency = _currency_from_user(row)
    direct   = get_direct_only(message.from_user.id)
    sym      = SYM.get(currency, "₽")

    wait = await message.answer(f"📅 Строю календарь {data['origin_name']} → {name}...")
    days = []; err = ""
    try:
        days = await get_month_calendar(data["origin"], iata, currency, direct)
    except Exception as e:
        logger.error("calendar error: %s", e)
        err = "😔 Данные календаря временно недоступны."

    if not days:
        await wait.edit_text(err or f"😔 Нет данных для {data['origin_name']} → {name}.")
        return

    lines = [f"📅 <b>Дешевейшие дни</b>: {data['origin_name']} → {name}\n"]
    for i, d in enumerate(days[:10], 1):
        tr = "🟢" if d.transfers == 0 else "🔁"
        lines.append(
            f"{i}. <b>{d.date}</b>  {tr}  💰 <b>{d.price:,} {sym}</b>"
            f"  <a href=\"{html.escape(d.link)}\">Купить</a>"
        )
    if len(days) > 10:
        lines.append(f"\n<i>Показаны 10 лучших из {len(days)} дней</i>")
    await wait.edit_text("\n".join(lines), disable_web_page_preview=True)


# ── ЖД БИЛЕТЫ ─────────────────────────────────────────────────────────────

@router.message(Command("train"))
@router.message(F.text == "🚂 ЖД билеты")
async def cmd_train(message: Message, state: FSMContext):
    if not await _reg(message):
        return
    row  = get_user(message.from_user.id)
    city = _city_from_user(row)
    await state.set_state(SearchTrain.origin)
    await state.update_data(default_city=city)
    await message.answer(
        "🚂 <b>Поиск ЖД билетов через Tutu.ru</b>\n\n"
        "1️⃣ Введи откуда и куда\n"
        "2️⃣ Укажи дату\n"
        "3️⃣ Получи ссылку → выбирай поезд, покупай\n\n"
        f"Шаг 1/3. Откуда едем?\n"
        f"Город по умолч.: <b>{_city_name(city)}</b>",
        reply_markup=skip_kb(_city_name(city)),
    )


@router.message(SearchTrain.origin)
async def fsm_train_origin(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    data = await state.get_data()
    if message.text.startswith("➡️"):
        iata = data["default_city"]
        name = _city_name(iata)
    else:
        station = resolve_train_station(message.text.strip())
        if station:
            name = station[1]
            res  = resolve_iata(message.text.strip())
            iata = res[0] if res else message.text.strip().upper()[:3]
        else:
            result = await resolve_iata_async(message.text.strip())
            if not result:
                await message.answer("❌ Город не найден.")
                return
            iata, name = result
    await state.update_data(origin=iata, origin_name=name)
    await state.set_state(SearchTrain.destination)
    await message.answer(f"✅ Откуда: <b>{name}</b>\n\nШаг 2/3. Куда едем?", reply_markup=cancel_kb())


@router.message(SearchTrain.destination)
async def fsm_train_dest(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    station = resolve_train_station(message.text.strip())
    if station:
        name = station[1]
        res  = resolve_iata(message.text.strip())
        iata = res[0] if res else message.text.strip().upper()[:3]
    else:
        result = await resolve_iata_async(message.text.strip())
        if not result:
            await message.answer("❌ Город не найден.")
            return
        iata, name = result
    await state.update_data(destination=iata, dest_name=name)
    await state.set_state(SearchTrain.date)
    tmrw = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    await message.answer(
        f"✅ Куда: <b>{name}</b>\n\n"
        f"Шаг 3/3. Дата поездки (<code>YYYY-MM-DD</code>):\n"
        f"Например: <code>{tmrw}</code>",
        reply_markup=cancel_kb(),
    )


@router.message(SearchTrain.date)
async def fsm_train_date(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    date = message.text.strip()
    if not _valid_date(date):   # FIX: проверяем что дата не в прошлом
        await message.answer(
            "❌ Формат: <code>2025-09-15</code>\n"
            "<i>Дата не может быть в прошлом.</i>"
        )
        return
    data = await state.get_data()
    await state.clear()

    try:
        train = get_train_link(data["origin"], data["destination"], date)
        add_history(message.from_user.id, "train", data["origin"], data["destination"], date, None, "rub")
        log_event(message.from_user.id, "search_train", f"{data['origin']}-{data['destination']}-{date}")
        text = (
            f"🚂 <b>ЖД: {train.origin_name} → {train.dest_name}</b>\n"
            f"📅 Дата: <b>{date}</b>\n\n"
            f"Нажми ссылку — Tutu.ru откроется с уже заполненным маршрутом.\n\n"
            f'🔗 <a href="{html.escape(train.link)}">Смотреть расписание и цены →</a>\n\n'
            f"<i>💡 Совет: покупай заранее — за 45–60 дней дешевле</i>"
        )
    except Exception as e:
        logger.error("Tutu link error: %s", e)
        text = "😔 Не удалось сформировать ссылку.\nПопробуй на <a href='https://www.tutu.ru'>tutu.ru</a>"

    await message.answer(text, reply_markup=main_menu(), disable_web_page_preview=True)


# ── ГОРЯЩИЕ + ERROR FARES ─────────────────────────────────────────────────

@router.message(Command("deals"))
@router.message(F.text == "🔥 Горящие")
async def cmd_deals(message: Message):
    if not await _reg(message):
        return
    row      = get_user(message.from_user.id)
    city     = _city_from_user(row)
    currency = _currency_from_user(row)
    direct   = get_direct_only(message.from_user.id)
    sym      = SYM.get(currency, "₽")

    wait = await message.answer(f"🔥 Ищу горящие из <b>{_city_name(city)}</b>...")

    # 1. Error fares (аномально низкие цены)
    special = []
    try:
        special = await get_special_offers(city, currency, limit=4)
    except Exception as e:
        logger.error("special_offers: %s", e)

    # 2. Свежие из кэша
    latest = []
    try:
        latest = await search_latest(city, currency=currency, limit=10, direct_only=direct)
    except Exception as e:
        logger.error("deals latest: %s", e)

    if not special and not latest:
        await wait.edit_text(
            f"😔 Горящих из {_city_name(city)} сейчас нет.\n"
            "Попробуй позже или смени город в /settings"
        )
        return

    lines = [f"🔥 <b>Горящие предложения из {_city_name(city)}</b>\n"]

    if special:
        lines.append("🚨 <b>Error fares — аномально низкие:</b>")
        for i, t in enumerate(special, 1):
            tr = "🟢" if t.transfers == 0 else "🔁"
            rt = f" ↔ {t.return_date[:7]}" if t.return_date else ""
            lines.append(
                f"{i}. ✈️ <b>{t.destination}</b>  {t.depart_date[:7]}{rt}"
                f"  {tr}  💰 <b>{t.price:,} {sym}</b>\n"
                f"   <a href=\"{html.escape(t.link)}\">Купить</a>"
            )
        lines.append("")

    if latest:
        lines.append("✈️ <b>Свежие дешёвые:</b>")
        for i, t in enumerate(latest[:6], 1):
            tr = "🟢" if t.transfers == 0 else "🔁"
            lines.append(
                f"{i}. ✈️ <b>{t.destination}</b>  {t.depart_date[:7]}"
                f"  {tr}  💰 <b>{t.price:,} {sym}</b>\n"
                f"   <a href=\"{html.escape(t.link)}\">Купить</a>"
            )

    # ЖД популярные маршруты
    try:
        train_routes = get_popular_routes(city)
        if train_routes:
            lines.append("\n🚂 <b>Популярные ЖД из твоего города:</b>")
            for r in train_routes:
                lines.append(f"• {r.dest_name}  <a href=\"{html.escape(r.link)}\">Расписание →</a>")
    except Exception as e:
        logger.error("train routes: %s", e)

    log_event(message.from_user.id, "deals", city)
    await wait.edit_text("\n".join(lines), disable_web_page_preview=True)


# ── АЛЕРТЫ ────────────────────────────────────────────────────────────────

@router.message(Command("alert"))
async def cmd_alert_start(message: Message, state: FSMContext):
    if not await _reg(message):
        return
    plan  = get_user_plan(message.from_user.id)
    limit = MAX_ALERTS_PRO if plan == "pro" else MAX_ALERTS_FREE
    if count_alerts(message.from_user.id) >= limit:
        await message.answer(
            f"❌ Лимит {limit} алертов для тарифа <b>{plan}</b>.\n"
            f"Удали один через /alerts."
        )
        return
    row  = get_user(message.from_user.id)
    city = _city_from_user(row)
    await state.set_state(AddAlert.origin)
    await state.update_data(default_city=city)
    await message.answer(
        "🔔 <b>Новый алерт</b>\n\n"
        "Как только цена упадёт ниже твоего порога — пришлю уведомление.\n\n"
        f"Шаг 1/5. Откуда? (умолч.: <b>{_city_name(city)}</b>)",
        reply_markup=skip_kb(_city_name(city)),
    )


@router.message(AddAlert.origin)
async def fsm_alert_origin(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    data = await state.get_data()
    if message.text.startswith("➡️"):
        iata = data["default_city"]
        name = _city_name(iata)
    else:
        res = await resolve_iata_async(message.text.strip())
        if not res:
            await message.answer("❌ Город не найден.")
            return
        iata, name = res
    await state.update_data(origin=iata, origin_name=name)
    await state.set_state(AddAlert.destination)
    await message.answer(f"✅ {name}\n\nШаг 2/5. Куда?", reply_markup=cancel_kb())


@router.message(AddAlert.destination)
async def fsm_alert_dest(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    res = await resolve_iata_async(message.text.strip())
    if not res:
        await message.answer("❌ Город не найден.")
        return
    iata, name = res
    await state.update_data(destination=iata, dest_name=name)
    await state.set_state(AddAlert.month)
    await message.answer(f"✅ {name}\n\nШаг 3/5. Месяц вылета (<code>YYYY-MM</code>):", reply_markup=cancel_kb())


@router.message(AddAlert.month)
async def fsm_alert_month(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    if not _valid_month(message.text.strip()):
        await message.answer("❌ Формат: <code>2025-09</code>")
        return
    await state.update_data(month=message.text.strip())
    await state.set_state(AddAlert.return_month)
    await message.answer(
        f"✅ Вылет: <b>{message.text.strip()}</b>\n\n"
        f"Шаг 4/5. Месяц обратного рейса (или пропусти — только туда):",
        reply_markup=skip_kb("Только туда"),
    )


@router.message(AddAlert.return_month)
async def fsm_alert_return_month(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    return_month = ""
    if not message.text.startswith("➡️"):
        rm = message.text.strip()
        if not _valid_month(rm):
            await message.answer("❌ Формат: <code>2025-10</code>, или нажми «➡️ Только туда».")
            return
        return_month = rm
    await state.update_data(return_month=return_month)
    await state.set_state(AddAlert.threshold)
    row = get_user(message.from_user.id)
    sym = SYM.get(_currency_from_user(row), "₽")
    await message.answer(
        f"Шаг 5/5. Пороговая цена ({sym}):\n"
        f"Пришлю алерт когда цена упадёт <b>ниже</b> этой суммы.\n"
        f"Например: <code>8000</code>",
        reply_markup=cancel_kb(),
    )


@router.message(AddAlert.threshold)
async def fsm_alert_threshold(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    txt = message.text.strip().replace(" ", "")
    if not txt.isdigit() or int(txt) < 100:
        await message.answer("❌ Введи число больше 100.")
        return
    data = await state.get_data()
    await state.clear()
    row = get_user(message.from_user.id)
    sym = SYM.get(_currency_from_user(row), "₽")
    return_month = data.get("return_month", "")
    aid = add_alert(
        message.from_user.id, "avia",
        data["origin"], data["destination"],
        data["month"], int(txt), return_month,
    )
    log_event(message.from_user.id, "alert_created", str(aid))
    rt_str = f" ↔ {data['dest_name']} ({return_month})" if return_month else f" → {data['dest_name']}"
    await message.answer(
        f"✅ <b>Алерт #{aid} создан!</b>\n\n"
        f"✈️ {data['origin_name']}{rt_str}\n"
        f"📅 Вылет: {data['month']}\n"
        f"💰 Порог: <b>{int(txt):,} {sym}</b>\n\n"
        f"Проверяю цены каждый час — как только упадёт, напишу. 🎯",
        reply_markup=main_menu(),
    )


@router.message(Command("alerts"))
@router.message(F.text == "🔔 Мои алерты")
async def cmd_alerts(message: Message):
    if not await _reg(message):
        return
    rows = get_user_alerts(message.from_user.id)
    if not rows:
        await message.answer("У тебя нет алертов.\nСоздай через /alert")
        return
    row = get_user(message.from_user.id)
    sym = SYM.get(_currency_from_user(row), "₽")
    for a in rows:
        kind   = "✈️" if a["kind"] == "avia" else "🚂"
        status = "▶️" if a["is_active"] else "⏸"
        fired  = f"  🔔 {a['fired_count']} срабатываний" if a["fired_count"] else ""
        last   = f"\n💸 Последняя цена: {a['last_price']:,} {sym}" if a["last_price"] else ""
        rt_str = f" ↔ {a['destination']} ({a['return_month']})" if a.get("return_month") else f" → {a['destination']}"
        await message.answer(
            f"<b>#{a['id']}</b> {kind} {status}{fired}\n"
            f"{a['origin']}{rt_str}\n"
            f"📅 {a['depart_month']}\n"
            f"💰 Порог: <b>{a['threshold']:,} {sym}</b>{last}",
            reply_markup=alert_kb(a["id"], bool(a["is_active"])),
        )


@router.callback_query(F.data.startswith("del:"))
async def cb_del(callback: CallbackQuery):
    remove_alert(callback.from_user.id, int(callback.data.split(":")[1]))
    await callback.message.edit_text("🗑 Алерт удалён.")
    await callback.answer()


@router.callback_query(F.data.startswith("pause:"))
async def cb_pause(callback: CallbackQuery):
    set_alert_active(int(callback.data.split(":")[1]), False)
    await callback.message.edit_text(callback.message.html_text + "\n\n<i>⏸ Приостановлен.</i>")
    await callback.answer()


@router.callback_query(F.data.startswith("resume:"))
async def cb_resume(callback: CallbackQuery):
    set_alert_active(int(callback.data.split(":")[1]), True)
    await callback.message.edit_text(callback.message.html_text + "\n\n<i>▶️ Возобновлён.</i>")
    await callback.answer()


# ── ИСТОРИЯ ───────────────────────────────────────────────────────────────

@router.message(Command("history"))
async def cmd_history(message: Message):
    if not await _reg(message):
        return
    rows = get_history(message.from_user.id, 10)
    if not rows:
        await message.answer("📭 История поисков пуста.\nНачни искать билеты — сохраняю автоматически.")
        return
    row = get_user(message.from_user.id)
    sym = SYM.get(_currency_from_user(row), "₽")
    lines = ["🕐 <b>История поисков</b>\n"]
    for h in rows:
        kind  = "✈️" if h["kind"] == "avia" else "🚂"
        price = f"  💰 от {h['min_price']:,} {sym}" if h["min_price"] else ""
        when  = str(h["created_at"])[:16]
        lines.append(
            f"{kind} <b>{h['origin']} → {h['destination']}</b>\n"
            f"   {h['query_param']}{price}  <i>{when}</i>"
        )
    await message.answer("\n\n".join(lines))


# ── СТАТИСТИКА ─────────────────────────────────────────────────────────────

@router.message(Command("stats"))
@router.message(F.text == "📊 Статистика")
async def cmd_stats(message: Message):
    if not await _reg(message):
        return
    s      = get_savings_stats(message.from_user.id)
    row    = get_user(message.from_user.id)
    sym    = SYM.get(_currency_from_user(row), "₽")
    direct = "включён" if get_direct_only(message.from_user.id) else "выключен"
    plan   = get_user_plan(message.from_user.id)

    await message.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"🔍 Поисков: <b>{s['searches']}</b>\n"
        f"🔔 Алертов сработало: <b>{s['alerts_fired']}</b>\n"
        f"💰 Выгодных сделок: <b>{s['deals']}</b>\n"
        f"🎉 Суммарная экономия: <b>{s['total_saved']:,} {sym}</b>\n"
        + (f"🏆 Лучшая цена по алерту: <b>{s['best_price']:,} {sym}</b>\n" if s["best_price"] else "")
        + f"\n⭐ Тариф: <b>{plan}</b>\n"
        f"✈️ Фильтр прямых: <i>{direct}</i>"
    )


# ── ПОДЕЛИТЬСЯ ────────────────────────────────────────────────────────────

@router.message(Command("share"))
async def cmd_share(message: Message):
    await message.answer(
        "📤 <b>Поделиться ботом</b>\n\n"
        f"Ссылка: <code>https://t.me/{BOT_USERNAME}</code>\n\n"
        "Нажми кнопку ниже чтобы отправить другу 🎁",
        reply_markup=share_kb(BOT_USERNAME),
    )


@router.callback_query(F.data == "copy_link")
async def cb_copy(callback: CallbackQuery):
    await callback.answer(f"Ссылка: https://t.me/{BOT_USERNAME}", show_alert=True)


# ── НАСТРОЙКИ ─────────────────────────────────────────────────────────────

@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: Message):
    if not await _reg(message):
        return
    row    = get_user(message.from_user.id)
    city   = _city_from_user(row)
    cur    = _currency_from_user(row)
    direct = "✅ только прямые" if get_direct_only(message.from_user.id) else "🔀 все рейсы"
    plan   = get_user_plan(message.from_user.id)
    await message.answer(
        f"⚙️ <b>Настройки</b>\n\n"
        f"🏙 Город: <b>{_city_name(city)}</b>\n"
        f"💱 Валюта: <b>{cur.upper()}</b>\n"
        f"✈️ Фильтр: <b>{direct}</b>\n"
        f"⭐ Тариф: <b>{plan}</b>\n\n"
        f"/setcity — изменить город\n"
        f"/setcurrency — изменить валюту\n"
        f"/setdirect — переключить фильтр прямых\n"
        f"/history — история поисков\n"
        f"/share — поделиться ботом"
    )


@router.message(Command("setcity"))
async def cmd_setcity(message: Message, state: FSMContext):
    if not await _reg(message):
        return
    await state.set_state(SetCity.waiting)
    await message.answer("🏙 Введи новый город вылета:", reply_markup=cancel_kb())


@router.message(SetCity.waiting, F.text != "❌ Отмена")
async def fsm_setcity(message: Message, state: FSMContext):
    res = await resolve_iata_async(message.text.strip())
    if not res:
        await message.answer("❌ Город не найден.")
        return
    iata, name = res
    set_city(message.from_user.id, iata)
    await state.clear()
    await message.answer(f"✅ Город обновлён: <b>{name} ({iata})</b>", reply_markup=main_menu())


@router.message(Command("setcurrency"))
async def cmd_setcurrency(message: Message):
    await message.answer("💱 Выбери валюту:", reply_markup=currency_inline())


@router.callback_query(F.data.startswith("cur:"))
async def cb_currency(callback: CallbackQuery, state: FSMContext):
    cur = callback.data.split(":")[1]
    current = await state.get_state()
    if current == Onboarding.currency.state:
        await onboard_currency(callback, state)
        return
    set_currency(callback.from_user.id, cur)
    await callback.message.edit_text(f"✅ Валюта: <b>{cur.upper()} {SYM.get(cur,'')}</b>")
    await callback.answer()


@router.message(Command("setdirect"))
async def cmd_setdirect(message: Message):
    if not await _reg(message):
        return
    new_val = not get_direct_only(message.from_user.id)
    set_direct_only(message.from_user.id, new_val)
    status = "✅ включён — только прямые" if new_val else "🔀 выключен — все рейсы"
    await message.answer(f"✈️ Фильтр прямых рейсов: <b>{status}</b>")


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    await message.answer(
        "<b>Команды</b>\n\n"
        "✈️ /search — авиабилеты (туда / туда-обратно)\n"
        "🚂 /train — ЖД билеты (Tutu.ru)\n"
        "📅 /calendar — календарь дешёвых дней\n"
        "🔥 /deals — горящие + error fares\n"
        "🔔 /alert — создать алерт на цену\n"
        "📋 /alerts — мои алерты\n"
        "🕐 /history — история поисков\n"
        "📊 /stats — статистика экономии\n"
        "📤 /share — поделиться ботом\n"
        "⚙️ /settings — город, валюта, фильтры\n"
        "/setdirect — вкл/выкл прямые рейсы\n\n"
        "<b>Формат:</b>\n"
        "Месяц: <code>2025-09</code>\n"
        "Дата ЖД: <code>2025-09-15</code>\n"
        "Города: по-русски или IATA (MOW, LED, AER)"
    )


@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_menu())
