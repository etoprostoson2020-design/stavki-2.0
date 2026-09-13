"""Time Machine и Leakage Firewall.

Защита двухслойная.

1. **Структурная.** Признак получает не весь датасет, а `HistoryView` — срез,
   в котором физически нет матчей текущего и последующих синхронных блоков.
   Увидеть будущее нельзя, потому что его нет в переданном объекте.
2. **Поведенческая.** `leakage_regression_test` портит все матчи начиная
   с некоторого блока и проверяет, что признаки более ранних матчей не
   изменились ни на одно значение. Ловит утечку через общее состояние.

Граница проводится по синхронному блоку, а не по времени: в сезонах, где
источник не даёт время начала, порядок матчей внутри дня неизвестен, и
считать их видящими друг друга нельзя.
"""
from __future__ import annotations

import dataclasses as dc
import datetime as dt
from collections import defaultdict, deque
from typing import Callable, Iterable

import numpy as np


@dc.dataclass(frozen=True)
class MatchRecord:
    """Завершённый матч в истории команды. Только то, что уже произошло."""
    fixture_id: int
    season: str
    sync_batch: int
    kickoff_utc: dt.datetime
    team: str
    opponent: str
    is_home: bool
    gf: int | None
    ga: int | None
    points: int | None
    stats: dict


class HistoryView:
    """Прошлое одной команды на момент матча. Будущего в объекте нет."""

    __slots__ = ("_records", "boundary_batch", "season")

    def __init__(self, records: Iterable[MatchRecord], boundary_batch: int, season: str):
        self._records = tuple(records)
        self.boundary_batch = boundary_batch
        self.season = season
        for r in self._records:
            if r.sync_batch >= boundary_batch:
                raise LeakageError(
                    f"в истории оказался матч из блока {r.sync_batch} "
                    f"при границе {boundary_batch}")

    def __len__(self) -> int:
        return len(self._records)

    def last(self, n: int) -> tuple[MatchRecord, ...]:
        return self._records[-n:] if n else ()

    def all(self) -> tuple[MatchRecord, ...]:
        return self._records


class LeakageError(RuntimeError):
    """Попытка прочитать данные, недоступные до стартового свистка."""


class TimeMachine:
    """Выдаёт состояние мира на момент каждого матча, блок за блоком."""

    def __init__(self, fixtures: list[dict], *, season_reset: bool = True):
        self.fixtures = sorted(fixtures, key=lambda f: (f["sync_batch"], f["fixture_id"]))
        self.season_reset = season_reset

    def _key(self, season: str, team: str):
        return (season, team) if self.season_reset else ("_", team)

    def walk(self) -> Iterable[tuple[dict, HistoryView, HistoryView]]:
        """Идёт по блокам и для каждого матча отдаёт историю хозяев и гостей.

        Результаты блока добавляются в состояние только после того, как все
        матчи блока обработаны, поэтому матчи одного блока не видят друг друга.
        """
        state: dict[tuple, deque[MatchRecord]] = defaultdict(lambda: deque(maxlen=64))
        by_batch: dict[int, list[dict]] = defaultdict(list)
        for f in self.fixtures:
            by_batch[f["sync_batch"]].append(f)

        for batch in sorted(by_batch):
            group = by_batch[batch]
            for f in group:
                hv = HistoryView(state[self._key(f["season"], f["home_team"])], batch, f["season"])
                av = HistoryView(state[self._key(f["season"], f["away_team"])], batch, f["season"])
                yield f, hv, av
            for f in group:                       # состояние обновляется ПОСЛЕ блока
                for team, opp, home in ((f["home_team"], f["away_team"], True),
                                        (f["away_team"], f["home_team"], False)):
                    gf = f["fthg"] if home else f["ftag"]
                    ga = f["ftag"] if home else f["fthg"]
                    pts = None if gf is None or ga is None else (3 if gf > ga else 1 if gf == ga else 0)
                    state[self._key(f["season"], team)].append(MatchRecord(
                        fixture_id=f["fixture_id"], season=f["season"], sync_batch=batch,
                        kickoff_utc=f["kickoff_utc"], team=team, opponent=opp, is_home=home,
                        gf=gf, ga=ga, points=pts, stats=f.get("stats") or {}))


def leakage_regression_test(fixtures: list[dict],
                            compute: Callable[[list[dict]], dict[int, dict[str, float | None]]],
                            *, n_points: int = 6, seed: int = 7) -> dict:
    """Портит будущее и проверяет, что прошлое не дрогнуло.

    Возвращает отчёт; `discrepancies == 0` — обязательное условие активации
    любого признака.
    """
    rng = np.random.default_rng(seed)
    base = compute(fixtures)
    batches = np.array(sorted({f["sync_batch"] for f in fixtures}))
    candidates = batches[len(batches) // 6:]          # не трогаем самое начало: там мало истории
    picks = rng.choice(candidates, size=min(n_points, len(candidates)), replace=False)

    per_point, total = [], 0
    for b in sorted(int(x) for x in picks):
        idx = [i for i, f in enumerate(fixtures) if f["sync_batch"] >= b]
        corrupted = [dict(f) for f in fixtures]
        for f in corrupted:
            f["stats"] = dict(f.get("stats") or {})

        # Перестановка КАЖДОГО поля независимо, а не строк целиком.
        # Строчная перестановка сохраняет пары (забито, пропущено) и потому
        # не меняет сезонные агрегаты команды — утечка через итоговую таблицу
        # осталась бы незамеченной.
        stat_keys = sorted({k for f in fixtures for k in (f.get("stats") or {})})
        for field in ("fthg", "ftag"):
            vals = [corrupted[i][field] for i in idx]
            for i, v in zip(idx, rng.permutation(np.array(vals, dtype=object))):
                corrupted[i][field] = v
        for key in stat_keys:
            vals = [corrupted[i]["stats"].get(key) for i in idx]
            for i, v in zip(idx, rng.permutation(np.array(vals, dtype=object))):
                corrupted[i]["stats"][key] = v
        for i in idx:                       # исход пересчитывается по испорченному счёту
            a, c = corrupted[i]["fthg"], corrupted[i]["ftag"]
            corrupted[i]["ftr"] = (None if a is None or c is None
                                   else "H" if a > c else "A" if a < c else "D")
        n_bad_rows = len(idx)

        after = compute(corrupted)
        diff = 0
        for f in fixtures:
            if f["sync_batch"] >= b:
                continue
            a, c = base[f["fixture_id"]], after[f["fixture_id"]]
            for k in a:
                x, y = a[k], c[k]
                if x is None and y is None:
                    continue
                if x is None or y is None or abs(x - y) > 1e-12:
                    diff += 1
        per_point.append({"batch": b, "corrupted_fixtures": n_bad_rows, "discrepancies": diff})
        total += diff

    return {"points": per_point, "discrepancies": total, "clean": total == 0}
