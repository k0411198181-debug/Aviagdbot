from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    city     = State()
    currency = State()
    direct   = State()


class SearchAvia(StatesGroup):
    origin       = State()
    destination  = State()
    month        = State()
    return_month = State()   # ← новый шаг: обратный рейс (опционально)


class SearchTrain(StatesGroup):
    origin      = State()
    destination = State()
    date        = State()


class CalendarSearch(StatesGroup):
    origin      = State()
    destination = State()


class AddAlert(StatesGroup):
    origin       = State()
    destination  = State()
    month        = State()
    return_month = State()   # ← новый шаг: обратный рейс (опционально)
    threshold    = State()


class SetCity(StatesGroup):
    waiting = State()
