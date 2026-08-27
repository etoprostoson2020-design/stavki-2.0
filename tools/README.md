# api_scout_test.py — выбор поставщика данных (EPL / La Liga)

Чистый stdlib, без pip. Ничего из приложения не трогает.

## Запуск

```bash
export APIFOOTBALL_KEY=...   # https://www.api-football.com/  (free: 100 req/day)
export ODDS_API_KEY=...      # https://the-odds-api.com/      (free: 500 credits/mo)
export ODDSPAPI_KEY=...      # https://oddspapi.io/           (free: 250 req/mo)

python3 tools/api_scout_test.py
```

Провайдер без ключа просто пропускается. Ключи читаются только из env.

Результат: `tools/api_scout_out/` — сырые ответы по каждому пробнику + `report.json`.

## Опционально (у OddsPapi есть рабочие дефолты из доков)

```bash
export ODDSPAPI_BASE='https://api.oddspapi.io/v4/odds-by-tournaments?tournamentIds={league}&apiKey={key}'
export ODDSPAPI_EPL=17     # tournamentId EPL
export ODDSPAPI_LALIGA=8   # tournamentId La Liga
```

## Что смотреть глазами в сыром JSON

| Файл | На что смотреть |
|---|---|
| `apifootball_fixtures_*.json` | `score.halftime` — заполнен ли; `fixture.date` + `fixture.timestamp` + `fixture.timezone`; `fixture.id` стабильность между прогонами |
| `apifootball_odds.json` | сколько объектов в `response[0].bookmakers`; `paging.total` |
| `theoddsapi_odds_*.json` | длина `bookmakers[]` на событие; `markets[].key == "totals"` c `point: 2.5`; `commence_time` (всегда UTC `Z`) |
| `theoddsapi_scores.json` | есть ли вообще разбивка по таймам в `scores[]` (ожидание: **нет**) |
| `oddspapi_odds_by_tournaments_no_bookmaker_param.json` | `distinct_books_in_response` — проверка заявления «1 запрос = 350+ книг» |
| `oddspapi_odds_single_fixture.json` | реальная глубина книг на один матч |
| `oddspapi_scores.json` | ключи периодов: `1` = первый тайм (HT) |

## Ключевой замер

В `report.json` у каждого провайдера есть `requests_per_round` — сколько вызовов
нужно на весь тур (2 лиги x 10 матчей) со всеми книгами. Это и есть метрика
line-shopping, а не цена одного запроса.

У OddsPapi специально сделаны два пробника `odds-by-tournaments`: с параметром
`bookmaker=pinnacle` и без него. Разница в `distinct_books_in_response` показывает,
отдаёт ли endpoint весь board или одну книгу за запрос.
