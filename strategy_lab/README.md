# FOOTBALL STRATEGY LAB

Исследовательская лаборатория футбольных стратегий. **Не приложение для ставок.**
Ищет, проверяет и замораживает стратегии; подтверждённые уходят в отдельный
Decision App через versioned JSON contract.

Реализация архитектурного пакета v1 (документы 01–10).

> **Размещение.** По документу 08 Strategy Lab и Decision App — разные системы.
> Сейчас лаборатория лежит подкаталогом `strategy_lab/` внутри репозитория
> Decision App. Это временно; при первом же экспорте её нужно вынести
> в собственный репозиторий, чтобы контракт между системами был настоящим.

## Статус

| Фаза | Состояние |
|---|---|
| 0. Repository & Infrastructure | готово |
| 1. Football-Data importer + Data Audit (один источник) | готово |
| 2. Canonical Data | готово (fixtures, team alias registry, lineage) |
| 3. Time Machine & Leakage Firewall | готово |
| 4. Feature Factory | ядро готово, каталог из 4 признаков |
| 5. Experiment Engine | готово (один воспроизводимый эксперимент) |
| 6–12 | не начаты |

Порядок фаз изменён против документа 10: Time Machine поднят до Canonical,
второй источник (API-Football) отложен. Обоснование — в
`../laliga_validation/architecture_review_v1.md`, раздел 10.

## Быстрый старт

```bash
cp .env.example .env          # секреты только здесь, в git не попадает
docker compose up -d          # postgres + redis + api + worker
make migrate                  # схема БД
make slice                    # первый vertical slice целиком
make test                     # тесты, включая Red Team
```

Без Docker (локальные postgres/redis):

```bash
export $(grep -v '^#' .env | xargs)
make migrate && make slice && make test
```

## Vertical slice

```
Football-Data CSV → RAW snapshot (sha256) → Data Audit → Canonical Fixtures
    → Time Machine (as_of) → Feature Factory → Experiment → result_hash
```

`make slice` печатает отчёт аудита, число канонических матчей, покрытие признаков
и результат эксперимента с хэшем. Повторный запуск обязан дать тот же хэш.

## Что здесь принципиально

- **Утечка блокируется технически.** Любой признак до активации проходит
  `LeakageFirewall`: все зависимости обязаны иметь `kickoff < kickoff` целевого
  матча, а при неизвестном времени начала — принадлежать более раннему
  синхронному блоку (в сезонах 16-17…18-19 у Football-Data нет столбца `Time`).
- **NULL никогда не 0.** Недостаток истории даёт `UNAVAILABLE`, а не ноль.
- **Хронология по kickoff, не по туру.** Столбца тура в источнике нет.
- **Воспроизводимость привязана к окружению.** `dataset_version` и `result_hash`
  включают лок зависимостей; хэш считается от канонически округлённых значений,
  никогда от сырых float.
- **Holdout Ledger.** Система знает, сколько неоткрытых сезонов осталось в лиге,
  и отказывается запускать discovery, если батч обнуляет остаток.
