# 02. Модель данных

Четыре слоя по п. 3 ТЗ: `raw` → `core` → `features` → `strategies`.
Первые три — Parquet, читаемые DuckDB. Четвёртый — SQLite.

---

## Слой raw — сырые ответы, иммутабельно

```
data/raw/api_football/endpoint=fixtures/league=39/season=2016/part-0000.jsonl.zst
data/raw/api_football/endpoint=fixture_statistics/league=39/season=2016/...
data/raw/api_football/endpoint=fixture_events/league=39/season=2016/...
data/raw/football_data/div=SP1/season=1617/SP1.csv
```

Обёртка каждой записи:

| Поле | Тип | Смысл |
|---|---|---|
| `fetched_at_utc` | timestamp | когда получено |
| `endpoint` | text | `/fixtures`, `/fixtures/statistics`, … |
| `params_json` | text | точные параметры запроса |
| `http_status` | int | код ответа |
| `response_json` | text | тело ответа как есть |
| `payload_sha256` | text | хеш тела, для дедупликации и дельта-обновлений |
| `api_version` | text | версия схемы ответа на момент забора |

Правило: **слой append-only и никогда не редактируется.** Изменился парсер —
пересобираем `core` из `raw` без единого запроса к API. Это же даёт вечный кэш
из п. 2 ТЗ: сыгранный матч выкачивается один раз.

---

## Слой core — нормализованные сущности

Ниже DDL в нотации DuckDB. Все временные метки — UTC.

```sql
CREATE TABLE core.league (
  league_id      INTEGER PRIMARY KEY,   -- id из API-Football
  name           TEXT NOT NULL,
  country        TEXT NOT NULL,
  tier           SMALLINT NOT NULL,     -- 1 = высший дивизион
  fd_div_code    TEXT,                  -- код football-data.co.uk: E0, SP1, I2…
  default_tz     TEXT NOT NULL,
  is_cup         BOOLEAN DEFAULT FALSE,
  active         BOOLEAN DEFAULT TRUE
);

CREATE TABLE core.season (
  league_id      INTEGER NOT NULL,
  season         INTEGER NOT NULL,      -- 2016 = сезон 2016/17
  start_date     DATE, end_date DATE,
  n_teams        SMALLINT, n_rounds SMALLINT,
  coverage_json  TEXT,                  -- что реально отдаёт тариф: stats/events/lineups/xg
  PRIMARY KEY (league_id, season)
);

CREATE TABLE core.team (
  team_id     INTEGER PRIMARY KEY,
  name        TEXT NOT NULL, short_name TEXT, country TEXT, founded SMALLINT
);

CREATE TABLE core.team_alias (             -- маппинг названий CSV на id API
  source        TEXT NOT NULL,             -- 'football_data'
  source_name   TEXT NOT NULL,             -- 'Ath Bilbao'
  team_id       INTEGER NOT NULL,
  confidence    REAL NOT NULL,             -- 1.0 = подтверждено вручную
  verified_by   TEXT, verified_at TIMESTAMP,
  PRIMARY KEY (source, source_name)
);

CREATE TABLE core.venue (
  venue_id  INTEGER PRIMARY KEY,
  name TEXT, city TEXT, country TEXT,
  lat DOUBLE, lon DOUBLE,                 -- для километража выезда и погоды
  capacity INTEGER, surface TEXT, altitude_m INTEGER
);

CREATE TABLE core.referee (
  referee_id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT
);

CREATE TABLE core.match (
  match_id      BIGINT PRIMARY KEY,       -- fixture id API-Football
  league_id     INTEGER NOT NULL,
  season        INTEGER NOT NULL,
  round_no      SMALLINT,                 -- нормализованный номер тура
  kickoff_utc   TIMESTAMP NOT NULL,
  status        TEXT NOT NULL,            -- FT AET PEN PST CANC ABD AWD WO NS
  home_team_id  INTEGER NOT NULL,
  away_team_id  INTEGER NOT NULL,
  venue_id      INTEGER, referee_id INTEGER,
  ht_home SMALLINT, ht_away SMALLINT,     -- счёт первого тайма
  ft_home SMALLINT, ft_away SMALLINT,     -- основное время, база всех рынков
  et_home SMALLINT, et_away SMALLINT,
  pen_home SMALLINT, pen_away SMALLINT,
  attendance INTEGER,
  behind_closed_doors BOOLEAN,            -- ковидный флаг
  source        TEXT NOT NULL,            -- 'api' | 'football_data' | 'merged'
  ingested_at   TIMESTAMP NOT NULL,
  known_at      TIMESTAMP NOT NULL        -- kickoff + 130 мин
);
```

Правила по `status` (в ТЗ не оговорены, но обязаны быть):

- в аналитику и расчёт рынков идут только `FT`; кубковые `AET`/`PEN`
  учитываются по основному времени и помечаются;
- `AWD` и `WO` (техническое поражение) **исключаются из статистики**, но
  остаются в календаре — они влияют на отдых и серии;
- `PST`, `CANC`, `ABD` не дают строк витрины, но сдвигают календарные признаки.

```sql
CREATE TABLE core.match_stat (           -- две строки на матч
  match_id BIGINT NOT NULL, team_id INTEGER NOT NULL, is_home BOOLEAN NOT NULL,
  shots SMALLINT, shots_on SMALLINT, shots_off SMALLINT, shots_blocked SMALLINT,
  shots_inside SMALLINT, shots_outside SMALLINT,
  corners SMALLINT, offsides SMALLINT, fouls SMALLINT,
  yellow SMALLINT, red SMALLINT,
  possession_pct REAL, passes INTEGER, passes_acc INTEGER, saves SMALLINT,
  xg DOUBLE,                              -- NULL там, где источник не отдаёт
  source TEXT NOT NULL,
  PRIMARY KEY (match_id, team_id)
);

CREATE TABLE core.match_event (
  match_id BIGINT NOT NULL, seq SMALLINT NOT NULL,
  minute SMALLINT NOT NULL, minute_extra SMALLINT,
  team_id INTEGER, player_id INTEGER, assist_id INTEGER,
  type TEXT NOT NULL,                     -- Goal | Card | subst | Var
  detail TEXT,                            -- Normal Goal | Own Goal | Penalty | Yellow…
  PRIMARY KEY (match_id, seq)
);

CREATE TABLE core.lineup (
  match_id BIGINT NOT NULL, team_id INTEGER NOT NULL, player_id INTEGER NOT NULL,
  formation TEXT, is_start BOOLEAN NOT NULL, position TEXT, grid TEXT,
  known_at TIMESTAMP NOT NULL,            -- kickoff − 60 мин
  PRIMARY KEY (match_id, player_id)
);

CREATE TABLE core.player_season (        -- вес «ключевого игрока»
  player_id INTEGER, team_id INTEGER, league_id INTEGER, season INTEGER,
  minutes INTEGER, apps SMALLINT, goals SMALLINT, assists SMALLINT, rating REAL,
  PRIMARY KEY (player_id, team_id, league_id, season)
);

CREATE TABLE core.injury (
  player_id INTEGER NOT NULL, team_id INTEGER, match_id BIGINT,
  reported_at TIMESTAMP, type TEXT, reason TEXT,
  known_at TIMESTAMP NOT NULL,
  retro_trustworthy BOOLEAN NOT NULL      -- FALSE для исторических записей, см. С9
);
```

Два справочника, редактируемых из интерфейса (п. 4 ТЗ):

```sql
CREATE TABLE core.derby (
  league_id INTEGER, team_a_id INTEGER, team_b_id INTEGER,
  intensity SMALLINT,                     -- 1..3
  note TEXT,
  PRIMARY KEY (league_id, team_a_id, team_b_id)
);

CREATE TABLE core.regime_event (          -- границы смены режима, п. 8 ТЗ
  league_id INTEGER,                      -- NULL = все лиги
  from_date DATE NOT NULL, to_date DATE,
  kind TEXT NOT NULL, note TEXT
);
```

Стартовое наполнение `regime_event` (проверяется при реализации по официальным
источникам, даты ниже — ориентир для схемы):

| Что | Лиги | Когда |
|---|---|---|
| Введение VAR | Серия A, Бундеслига | сезон 2017/18 |
| Введение VAR | Ла Лига, Лига 1 | сезон 2018/19 |
| Введение VAR | АПЛ | сезон 2019/20 |
| Матчи без зрителей | все | март 2020 — весна 2021, точные окна по лигам |
| Пять замен | все | с июня 2020, дальше по-разному по лигам |
| Трактовка игры рукой | все | 2019/20 и 2021/22 |
| Ужесточение добавленного времени | АПЛ и далее | 2023/24 |

Флаг `behind_closed_doors` вычисляется из посещаемости и окна режима, а не
угадывается.

---

## Слой features — витрина «команда-матч»

Ключевая витрина по п. 3 ТЗ: каждый матч даёт две строки.

```sql
CREATE TABLE features.team_match (
  match_id BIGINT NOT NULL, team_id INTEGER NOT NULL,
  is_home BOOLEAN NOT NULL,
  league_id INTEGER, season INTEGER, round_no SMALLINT,
  kickoff_utc TIMESTAMP NOT NULL,
  opponent_team_id INTEGER NOT NULL,
  block TEXT NOT NULL,                    -- lab | val | test | forward
  -- далее ~200 колонок признаков, все с суффиксом семейства
  feature_set_version TEXT NOT NULL,
  built_at TIMESTAMP NOT NULL,
  built_as_of TIMESTAMP,                  -- срез, на котором строилось; NULL = полный
  PRIMARY KEY (match_id, team_id)
);
```

Партиционирование: `features/fs=v3/league=39/season=2019/*.parquet`. Версия
набора признаков в пути — обязательна: она позволяет держать две сборки рядом и
сравнивать их побайтово (главный тест на утечку).

Реестр признаков материализуется из кода, но хранится и в данных, потому что
валидатор обязан читать его метаданные:

```sql
CREATE TABLE features.registry (
  feature_name TEXT PRIMARY KEY,
  family TEXT NOT NULL,                   -- calendar | form | mean_reversion | table…
  dtype TEXT NOT NULL,
  source_tables TEXT NOT NULL,            -- для линтера утечки
  window_spec TEXT,                       -- '5m' | 'season_to_date' | NULL
  availability_offset_min INTEGER NOT NULL, -- за сколько минут до матча известен
  available_from_season INTEGER,          -- xG недоступен до 2021
  retro_trustworthy BOOLEAN NOT NULL,
  null_policy TEXT NOT NULL,              -- 'propagate' — заполнение нулями запрещено
  shrinkage TEXT,                         -- параметры сжатия к среднему
  description TEXT NOT NULL
);
```

`null_policy = 'propagate'` — реализация запрета из п. 14 ТЗ: подставлять пустые
значения вместо отсутствующих данных нельзя. Матч, где признак неизвестен, не
попадает в выборку стратегии, и это отражается в её `n`, а не маскируется.

---

## Слой strategies — app.sqlite

```sql
CREATE TABLE strategy (
  id TEXT PRIMARY KEY,                    -- str_0417
  name TEXT NOT NULL, yaml TEXT NOT NULL,
  spec_hash TEXT NOT NULL,                -- хеш нормализованного YAML
  origin TEXT NOT NULL,                   -- manual | mining
  mining_run_id TEXT, parent_id TEXT,
  status TEXT NOT NULL,                   -- draft|published|watch|rejected|broken
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE validation_run (
  id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL,
  feature_set_version TEXT NOT NULL, protocol TEXT NOT NULL,
  n_hypotheses_context INTEGER NOT NULL,  -- множественность, в которой оценивалась
  report_json TEXT NOT NULL,
  started_at TIMESTAMP, finished_at TIMESTAMP
);

CREATE TABLE mining_run (
  id TEXT PRIMARY KEY, config_json TEXT NOT NULL,
  n_hypotheses_tested BIGINT NOT NULL,    -- п. 7.1: журнал числа гипотез
  n_survived INTEGER NOT NULL,
  n_permutations INTEGER NOT NULL,
  perm_max_distribution TEXT,             -- база «лучшая находка на шуме»
  started_at TIMESTAMP, finished_at TIMESTAMP
);

CREATE TABLE forward_prediction (         -- append-only, хеш-цепочка
  id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, match_id BIGINT NOT NULL,
  predicted_at_utc TIMESTAMP NOT NULL,    -- строго до kickoff
  kickoff_utc TIMESTAMP NOT NULL,
  market TEXT NOT NULL, side TEXT NOT NULL,
  k_be_point REAL, k_be_conservative REAL, k_required REAL,
  odds_seen REAL, bookmaker TEXT,         -- вводит пользователь; см. С6
  prev_hash TEXT, row_hash TEXT NOT NULL
);

CREATE TABLE forward_result (
  prediction_id TEXT PRIMARY KEY, settled_at TIMESTAMP,
  outcome TEXT NOT NULL,                  -- WIN HALF_WIN PUSH HALF_LOSS LOSS
  return_units REAL
);

CREATE TABLE api_budget (
  day DATE NOT NULL, minute_bucket TIMESTAMP NOT NULL, endpoint TEXT NOT NULL,
  n_requests INTEGER, n_errors INTEGER, n_429 INTEGER,
  PRIMARY KEY (day, minute_bucket, endpoint)
);

CREATE TABLE block_access_log (           -- сколько раз смотрели в закрытые блоки
  id INTEGER PRIMARY KEY, block TEXT NOT NULL,
  strategy_id TEXT, run_id TEXT, accessed_at TIMESTAMP NOT NULL, reason TEXT
);

CREATE TABLE job (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, params_json TEXT,
  state TEXT NOT NULL, progress REAL, error TEXT, created_at TIMESTAMP
);
```

Две таблицы заслуживают отдельного внимания:

**`forward_prediction` — append-only с хеш-цепочкой.** Каждая строка хранит хеш
предыдущей. Без этого журнал форвард-теста ничего не доказывает: задним числом
можно удалить неудачные прогнозы, и результат станет фикцией. Цепочка делает
задним числом отредактированный журнал очевидно сломанным. Поле `odds_seen`
пользователь заполняет в момент ставки — это единственный способ накопить
историю линии по экзотическим рынкам, которой в открытых источниках нет.

**`block_access_log`.** Каждое обращение стратегии к закрытому блоку — это
израсходованная степень свободы. Счётчик обращений входит в поправку на
множественность наравне с числом гипотез автомайнинга.

---

## Целостность

Проверки, запускаемые после каждой загрузки (расширение списка из скилла
`laliga-loader`):

1. в каждом сезоне высшего дивизиона ожидаемое число матчей и команд;
2. `ht_home <= ft_home` и `ht_away <= ft_away` — иначе битый счёт по таймам;
3. сумма голов из `match_event` совпадает с `ft_home + ft_away` (там, где
   события загружены);
4. `round_no` в диапазоне `1..n_rounds`, без дыр;
5. каждый `team_id` из CSV разрешён через `team_alias` с `confidence = 1.0`;
   неразрешённые попадают в очередь ручного маппинга, а не подставляются наугад;
6. нет матчей с `kickoff_utc`, попадающих в два тура одной команды;
7. `known_at > kickoff_utc` для всех фактов результата.
