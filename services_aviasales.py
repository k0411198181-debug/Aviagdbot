"""
aviasales.py — Travelpayouts Data API.

Эндпоинты:
  /v2/prices/cheap              — дешёвые билеты за месяц
  /v2/prices/latest             — свежие из кэша 48ч (горящие)
  /v2/prices/month-matrix       — цены на каждый день (Календарь)
  /aviasales/v3/get_special_offers    — аномально низкие / error fares
  /aviasales/v3/get_popular_directions — популярные направления

Shared aiohttp сессия: set_http_session() вызывается один раз при старте.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import aiohttp

from config import TP_MARKER, TP_TOKEN

logger = logging.getLogger(__name__)
BASE = "https://api.travelpayouts.com"
SYM  = {"rub": "₽", "usd": "$", "eur": "€", "try": "₺"}

# Единственная сессия на всё время работы бота
_http_session: Optional[aiohttp.ClientSession] = None


def set_http_session(session: aiohttp.ClientSession) -> None:
    global _http_session
    _http_session = session


@dataclass
class Ticket:
    origin:      str
    destination: str
    depart_date: str
    return_date: str
    price:       int
    transfers:   int
    airline:     str
    currency:    str
    link:        str


@dataclass
class CalendarDay:
    date:      str
    price:     int
    transfers: int
    currency:  str
    link:      str


def _link(origin: str, dest: str, depart: str, ret: str = "") -> str:
    """Партнёрская deep-link на Aviasales."""
    marker = TP_MARKER or ""
    try:
        dep_fmt = datetime.strptime(depart[:10], "%Y-%m-%d").strftime("%d%m")
    except Exception:
        dep_fmt = "0101"

    if ret:
        try:
            ret_fmt = datetime.strptime(ret[:10], "%Y-%m-%d").strftime("%d%m")
            path = f"{origin}{dep_fmt}{dest}1{ret_fmt}{origin}1"
        except Exception:
            path = f"{origin}{dep_fmt}{dest}1"
    else:
        path = f"{origin}{dep_fmt}{dest}1"

    return f"https://www.aviasales.ru/search/{path}?marker={marker}"


async def _get(endpoint: str, params: dict) -> dict:
    """HTTP GET через shared session (или временную если не инициализирована)."""
    params["token"] = TP_TOKEN

    async def _do(s: aiohttp.ClientSession) -> dict:
        async with s.get(
            f"{BASE}{endpoint}", params=params,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            if r.status != 200:
                logger.warning("Aviasales %s → HTTP %s", endpoint, r.status)
                return {}
            return await r.json()

    try:
        if _http_session and not _http_session.closed:
            return await _do(_http_session)
        async with aiohttp.ClientSession() as s:
            return await _do(s)
    except Exception as e:
        logger.error("Aviasales API error %s: %s", endpoint, e)
        return {}


# ── Основные функции ──────────────────────────────────────────────────────

async def search_cheapest(
    origin: str, destination: str,
    depart_month: str, currency: str = "rub",
    direct_only: bool = False,
    return_month: str = "",
) -> List[Ticket]:
    """Дешёвые билеты за месяц."""
    params: dict = {
        "currency":           currency,
        "origin":             origin,
        "destination":        destination,
        "depart_date":        depart_month,
        "show_to_affiliates": "true",
    }
    if return_month:
        params["return_date"] = return_month

    data    = await _get("/v2/prices/cheap", params)
    tickets = []
    raw     = data.get("data", {})
    dest_data = raw.get(destination.upper(), {}) if isinstance(raw, dict) else {}

    for item in dest_data.values():
        price     = int(item.get("price", 0))
        depart    = item.get("departure", "")
        transfers = item.get("transfers", 0)
        ret       = item.get("return", "") or ""
        if price > 0 and depart:
            if direct_only and transfers > 0:
                continue
            tickets.append(Ticket(
                origin=origin, destination=destination,
                depart_date=depart, return_date=ret,
                price=price, transfers=transfers,
                airline="", currency=currency,
                link=_link(origin, destination, depart, ret),
            ))
    return sorted(tickets, key=lambda t: t.price)[:8]


async def search_latest(
    origin: str, destination: str = "",
    currency: str = "rub", limit: int = 8,
    direct_only: bool = False,
) -> List[Ticket]:
    """Свежие из кэша 48ч."""
    params: dict = {
        "currency": currency, "origin": origin,
        "limit": limit, "show_to_affiliates": "true",
        "sorting": "price", "trip_class": 0,
    }
    if destination:
        params["destination"] = destination

    data    = await _get("/v2/prices/latest", params)
    tickets = []
    for item in data.get("data", []):
        price     = int(item.get("value", 0))
        depart    = item.get("depart_date", "")
        ret       = item.get("return_date", "") or ""
        dest      = item.get("destination", destination)
        transfers = item.get("number_of_changes", 0)
        if price > 0:
            if direct_only and transfers > 0:
                continue
            tickets.append(Ticket(
                origin=item.get("origin", origin), destination=dest,
                depart_date=depart, return_date=ret,
                price=price, transfers=transfers,
                airline=item.get("airline", ""), currency=currency,
                link=_link(origin, dest, depart, ret),
            ))
    return tickets


async def get_month_calendar(
    origin: str, destination: str,
    currency: str = "rub",
    direct_only: bool = False,
) -> List[CalendarDay]:
    """Цены на каждый день для Календаря."""
    data = await _get("/v2/prices/month-matrix", {
        "currency":           currency,
        "origin":             origin,
        "destination":        destination,
        "show_to_affiliates": "true",
    })
    days = []
    for item in data.get("data", []):
        price     = int(item.get("value", 0))
        depart    = item.get("depart_date", "")
        transfers = item.get("number_of_changes", 0)
        if price > 0 and depart:
            if direct_only and transfers > 0:
                continue
            days.append(CalendarDay(
                date=depart, price=price, transfers=transfers,
                currency=currency,
                link=_link(origin, destination, depart),
            ))
    return sorted(days, key=lambda d: d.price)


async def get_special_offers(
    origin: str,
    currency: str = "rub",
    limit: int = 6,
) -> List[Ticket]:
    """Error fares / аномально низкие цены (из v1)."""
    data = await _get("/aviasales/v3/get_special_offers", {
        "origin":   origin,
        "locale":   "ru",
        "currency": currency,
    })
    tickets = []
    for item in (data.get("data") or [])[:limit]:
        depart = (item.get("departure_at") or "")[:10]
        ret    = (item.get("return_at") or "")[:10]
        price  = int(item.get("price", 0))
        dest   = item.get("destination", "")
        if price > 0 and dest:
            tickets.append(Ticket(
                origin=origin, destination=dest,
                depart_date=depart, return_date=ret,
                price=price, transfers=item.get("number_of_changes", 0),
                airline=item.get("airline", ""), currency=currency,
                link=_link(origin, dest, depart, ret),
            ))
    return tickets


async def get_popular_destinations(
    origin: str,
    currency: str = "rub",
    limit: int = 10,
) -> List[Ticket]:
    """Популярные направления и лучшие цены из города (из v1)."""
    data = await _get("/aviasales/v3/get_popular_directions", {
        "origin":   origin,
        "locale":   "ru",
        "currency": currency.upper(),
        "limit":    limit,
        "page":     1,
    })
    tickets = []
    for item in (data.get("data") or {}).get("origin", []):
        depart = (item.get("departure_at") or "")[:10]
        ret    = (item.get("return_at") or "")[:10]
        dest   = item.get("destination") or item.get("city_iata", "")
        price  = int(item.get("price", 0))
        if price > 0 and dest:
            tickets.append(Ticket(
                origin=origin, destination=dest,
                depart_date=depart, return_date=ret,
                price=price, transfers=0,
                airline="", currency=currency,
                link=_link(origin, dest, depart, ret),
            ))
    return sorted(tickets, key=lambda t: t.price)


async def get_min_price(
    origin: str, destination: str, month: str,
    currency: str, return_month: str = "",
) -> Optional[int]:
    """Минимальная цена — для проверки алертов."""
    tickets = await search_cheapest(origin, destination, month, currency, return_month=return_month)
    if not tickets:
        tickets = await search_latest(origin, destination, currency)
    return min(t.price for t in tickets) if tickets else None
