import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import aiohttp
from config import TP_MARKER, TP_TOKEN

logger = logging.getLogger(__name__)
BASE = "https://api.travelpayouts.com"
SYM  = {"rub": "₽", "usd": "$", "eur": "€", "try": "₺"}

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


async def _get_v3(endpoint: str, params: dict) -> dict:
    headers = {
        "X-Access-Token": TP_TOKEN,
        "Accept": "application/json",
    }

    async def _do(s: aiohttp.ClientSession) -> dict:
        async with s.get(
            f"{BASE}{endpoint}", params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            if r.status != 200:
                logger.warning("Aviasales v3 %s -> HTTP %s", endpoint, r.status)
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


async def _get_v2(endpoint: str, params: dict) -> dict:
    params["token"] = TP_TOKEN

    async def _do(s: aiohttp.ClientSession) -> dict:
        async with s.get(
            f"{BASE}{endpoint}", params=params,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            if r.status != 200:
                logger.warning("Aviasales v2 %s -> HTTP %s", endpoint, r.status)
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


async def search_cheapest(
    origin: str, destination: str,
    depart_month: str, currency: str = "rub",
    direct_only: bool = False,
    return_month: str = "",
) -> List[Ticket]:
    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": depart_month,
        "currency": currency,
        "sorting": "price",
        "direct": "true" if direct_only else "false",
        "limit": 10,
        "page": 1,
        "one_way": "false" if return_month else "true",
    }
    if return_month:
        params["return_at"] = return_month

    data = await _get_v3("/aviasales/v3/prices_for_dates", params)
    tickets = []
    for item in data.get("data", []):
        price     = int(item.get("price", 0))
        depart    = (item.get("departure_at") or "")[:10]
        ret       = (item.get("return_at") or "")[:10]
        transfers = item.get("number_of_changes", 0)
        dest      = item.get("destination", destination)
        if price > 0 and depart:
            tickets.append(Ticket(
                origin=origin, destination=dest,
                depart_date=depart, return_date=ret,
                price=price, transfers=transfers,
                airline=item.get("airline", ""), currency=currency,
                link=_link(origin, dest, depart, ret),
            ))

    if not tickets:
        v2data = await _get_v2("/v2/prices/cheap", {
            "currency": currency,
            "origin": origin,
            "destination": destination,
            "depart_date": depart_month,
            "show_to_affiliates": "true",
        })
        raw = v2data.get("data", {})
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
    params = {
        "origin": origin,
        "currency": currency,
        "sorting": "price",
        "direct": "true" if direct_only else "false",
        "limit": limit,
        "page": 1,
        "one_way": "true",
    }
    if destination:
        params["destination"] = destination

    data = await _get_v3("/aviasales/v3/prices_for_dates", params)
    tickets = []
    for item in data.get("data", []):
        price     = int(item.get("price", 0))
        depart    = (item.get("departure_at") or "")[:10]
        ret       = (item.get("return_at") or "")[:10]
        dest      = item.get("destination", destination)
        transfers = item.get("number_of_changes", 0)
        if price > 0:
            tickets.append(Ticket(
                origin=item.get("origin", origin), destination=dest,
                depart_date=depart, return_date=ret,
                price=price, transfers=transfers,
                airline=item.get("airline", ""), currency=currency,
                link=_link(origin, dest, depart, ret),
            ))

    if not tickets:
        v2params = {
            "currency": currency,
            "origin": origin,
            "limit": limit,
            "show_to_affiliates": "true",
            "sorting": "price",
            "trip_class": 0,
        }
        if destination:
            v2params["destination"] = destination
        v2data = await _get_v2("/v2/prices/latest", v2params)
        for item in v2data.get("data", []):
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
    params = {
        "origin": origin,
        "destination": destination,
        "currency": currency,
        "sorting": "price",
        "direct": "true" if direct_only else "false",
        "limit": 30,
        "page": 1,
        "one_way": "true",
    }
    data = await _get_v3("/aviasales/v3/prices_for_dates", params)
    days = []
    for item in data.get("data", []):
        price     = int(item.get("price", 0))
        depart    = (item.get("departure_at") or "")[:10]
        transfers = item.get("number_of_changes", 0)
        if price > 0 and depart:
            days.append(CalendarDay(
                date=depart, price=price, transfers=transfers,
                currency=currency,
                link=_link(origin, destination, depart),
            ))

    if not days:
        v2data = await _get_v2("/v2/prices/month-matrix", {
            "currency": currency,
            "origin": origin,
            "destination": destination,
            "show_to_affiliates": "true",
        })
        for item in v2data.get("data", []):
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
    params = {
        "origin": origin,
        "currency": currency,
        "sorting": "price",
        "direct": "false",
        "limit": limit,
        "page": 1,
        "one_way": "true",
    }
    data = await _get_v3("/aviasales/v3/prices_for_dates", params)
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
    return await search_latest(origin, currency=currency, limit=limit)


async def get_min_price(
    origin: str, destination: str, month: str,
    currency: str, return_month: str = "",
) -> Optional[int]:
    tickets = await search_cheapest(
        origin, destination, month, currency,
        return_month=return_month
    )
    if not tickets:
        tickets = await search_latest(origin, destination, currency)
    return min(t.price for t in tickets) if tickets else None
