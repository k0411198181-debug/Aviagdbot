# ✈️🚂 TicketRadar Bot

Telegram-бот для поиска дешёвых авиабилетов и ЖД — на базе Travelpayouts API + Tutu.ru.

## Быстрый старт

```bash
# 1. Токены
# BOT_TOKEN  → @BotFather
# TP_TOKEN   → travelpayouts.com → Разработчикам → API
# TP_MARKER  → travelpayouts.com → Инструменты → Партнёрская ссылка

cp .env.example .env
nano .env

# 2. Локальный запуск
pip install -r requirements.txt
python app.py

# 3. Docker
docker-compose up -d --build
```

## Структура

```
ticketbot/
├── app.py                     # точка входа, shared aiohttp сессия
├── config.py                  # переменные окружения
├── bot/
│   ├── handlers.py            # все хэндлеры (авиа, ЖД, алерты, онбординг)
│   ├── admin_handlers.py      # /admin /ban /broadcast /setplan
│   ├── keyboards.py           # клавиатуры
│   └── fsm.py                 # FSM состояния
├── services/
│   ├── aviasales.py           # Travelpayouts API (авиа + error fares)
│   ├── tutu.py                # ЖД ссылки через Tutu.ru
│   ├── iata.py                # IATA справочник 130+ городов + API fallback
│   └── monitor.py             # фоновая проверка алертов
├── db/
│   ├── models.py              # схема SQLite + авто-миграция
│   └── queries.py             # SQL-запросы
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Онбординг (3 шага) или главное меню |
| `/search` | Авиабилеты туда / туда-обратно |
| `/train` | ЖД билеты (Tutu.ru) |
| `/calendar` | Календарь дешёвых дней |
| `/deals` | Горящие + error fares |
| `/alert` | Создать алерт на цену |
| `/alerts` | Мои алерты |
| `/history` | История поисков |
| `/stats` | Статистика экономии |
| `/settings` | Город, валюта, тарифы |
| `/setcity` | Сменить город вылета |
| `/setcurrency` | Сменить валюту |
| `/setdirect` | Вкл/выкл фильтр прямых рейсов |
| `/share` | Поделиться ботом |
| `/help` | Справка |

## Команды администратора

```
/makeadmin <ADMIN_SECRET>       — получить права
/admin                          — панель с метриками
/ban <user_id>                  — заблокировать
/unban <user_id>                — разблокировать
/setplan <user_id> <free|pro>   — изменить тариф
/broadcast <текст>              — рассылка всем
```

## Монетизация

Все ссылки содержат партнёрский маркер `TP_MARKER`.
При переходе и покупке — ~1.8% с авиабилета, ~1.5% с ЖД.

## Тарифы

| Тариф | Лимит алертов |
|---|---|
| free | 5 |
| pro | 30 |
| admin | 30 |

Тариф меняется через `/setplan <id> pro` (только для admin).

## Масштабирование при росте

- Замени `MemoryStorage` на `RedisStorage` при >1000 одновременных FSM-диалогов
- Замени SQLite на PostgreSQL + asyncpg при >10k пользователей
- Вынеси `check_all_alerts` в отдельный воркер

## Описание для BotFather

```
✈️🚂 TicketRadar — дешёвые авиабилеты и ЖД

🆓 Полностью бесплатно
🔔 Алерты — пришлю когда цена упадёт
📅 Календарь дешёвых дней
🔥 Горящие + аномально низкие цены
🚂 ЖД + Авиа в одном боте
📊 Статистика твоей экономии
```
