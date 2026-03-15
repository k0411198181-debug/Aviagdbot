"""
tutu.py — ЖД билеты через Tutu.ru (партнёрка Travelpayouts).

Реального API с ценами нет — генерируем партнёрскую ссылку
с заполненными полями (откуда, куда, дата). Пользователь
нажимает → попадает на Tutu.ru → покупает → комиссия ~1.5%.
"""

import logging
from dataclasses import dataclass
from typing import List

from config import TP_MARKER

logger = logging.getLogger(__name__)

# IATA → код станции Tutu
IATA_TO_TUTU = {
    "MOW": "2000000", "LED": "2004000", "OVB": "2060000",
    "SVX": "2030000", "KZN": "2060600", "GOJ": "2010000",
    "KRR": "2070000", "ROV": "2080000", "AER": "2090001",
    "KUF": "2040000", "UFA": "2050000", "PEE": "2032000",
    "OMS": "2062000", "KJA": "2064000", "IKT": "2066000",
    "KHV": "2100000", "VVO": "2102000", "VOZ": "2006000",
    "VOG": "2082000", "CEK": "2034000", "KGD": "2002000",
    "RTW": "2044000", "TOF": "2068000", "MMK": "2004920",
}

STATION_NAMES = {
    "2000000": "Москва",        "2004000": "Санкт-Петербург",
    "2060000": "Новосибирск",   "2030000": "Екатеринбург",
    "2060600": "Казань",        "2010000": "Нижний Новгород",
    "2070000": "Краснодар",     "2080000": "Ростов-на-Дону",
    "2090001": "Сочи",          "2040000": "Самара",
    "2050000": "Уфа",           "2032000": "Пермь",
    "2062000": "Омск",          "2064000": "Красноярск",
    "2066000": "Иркутск",       "2100000": "Хабаровск",
    "2102000": "Владивосток",   "2006000": "Воронеж",
    "2082000": "Волгоград",     "2002000": "Калининград",
    "2044000": "Саратов",       "2068000": "Томск",
    "2004920": "Мурманск",
}


@dataclass
class TrainLink:
    origin_name: str
    dest_name:   str
    date:        str
    link:        str
    note:        str = ""


def _tutu_link(from_code: str, to_code: str, date: str) -> str:
    """Партнёрская ссылка Tutu.ru."""
    marker   = TP_MARKER or ""
    date_fmt = date.replace("-", ".") if date else ""
    base     = f"https://www.tutu.ru/poezda/rasp_d.php?nnst1={from_code}&nnst2={to_code}"
    if date_fmt:
        base += f"&date={date_fmt}"
    if marker:
        return (
            f"https://c45.travelpayouts.com/click"
            f"?shmarker={marker}&promo_id=1770"
            f"&source_type=customlink&type=click"
            f"&custom_url={base}"
        )
    return base


def get_train_link(origin_iata: str, dest_iata: str, date: str) -> TrainLink:
    """Создаём ссылку на поиск ЖД билетов."""
    from_code = IATA_TO_TUTU.get(origin_iata.upper(), "2000000")
    to_code   = IATA_TO_TUTU.get(dest_iata.upper(), "2004000")
    from_name = STATION_NAMES.get(from_code, origin_iata)
    to_name   = STATION_NAMES.get(to_code, dest_iata)
    return TrainLink(
        origin_name=from_name, dest_name=to_name,
        date=date, link=_tutu_link(from_code, to_code, date),
        note="Цены и расписание на Tutu.ru",
    )


def get_popular_routes(origin_iata: str) -> List[TrainLink]:
    """Популярные ЖД маршруты из города."""
    from_code = IATA_TO_TUTU.get(origin_iata.upper(), "2000000")
    from_name = STATION_NAMES.get(from_code, origin_iata)
    popular   = [
        ("2000000", "Москва"), ("2004000", "Санкт-Петербург"),
        ("2060000", "Новосибирск"), ("2090001", "Сочи"), ("2070000", "Краснодар"),
    ]
    routes = []
    for to_code, to_name in popular:
        if to_code == from_code:
            continue
        routes.append(TrainLink(
            origin_name=from_name, dest_name=to_name,
            date="", link=_tutu_link(from_code, to_code, ""),
            note="Смотреть расписание и цены",
        ))
    return routes[:4]
