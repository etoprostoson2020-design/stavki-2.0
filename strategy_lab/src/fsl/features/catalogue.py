"""Каталог признаков MVP. Семейства FORM, GOALS, REST — по документу 03."""
from __future__ import annotations

from fsl.features.registry import REGISTRY, FeatureSpec, PreMatchContext
from fsl.temporal.time_machine import HistoryView


def _ppg(view: HistoryView, n: int) -> float | None:
    rec = [r for r in view.last(n) if r.points is not None]
    if len(rec) < n:
        return None                      # недостаток истории -> UNAVAILABLE, не 0
    return sum(r.points for r in rec) / n


def _avg_stat(view: HistoryView, n: int, key: str) -> float | None:
    vals = []
    for r in view.last(n):
        v = r.stats.get(key)
        if v is None:
            return None                  # пропуск в источнике -> UNAVAILABLE, не 0
        vals.append(v)
    if len(vals) < n:
        return None
    return sum(vals) / n


def _make(window: int):
    def ppg_diff(ctx: PreMatchContext, home: HistoryView, away: HistoryView):
        h, a = _ppg(home, window), _ppg(away, window)
        return None if h is None or a is None else h - a
    return ppg_diff


FORM_PPG_DIFF_5 = REGISTRY.register(FeatureSpec(
    feature_id="FORM_PPG_DIFF", version=1,
    name="Разница очков за матч, окно 5",
    family="FORM",
    description="Среднее очков хозяев за 5 последних завершённых матчей сезона "
                "минус то же у гостей. Считается строго по матчам более ранних "
                "синхронных блоков.",
    window=5, scope="ALL", season_transition="SEASON_RESET", minimum_history=5,
    compute=_make(5)))

FORM_PPG_DIFF_10 = REGISTRY.register(FeatureSpec(
    feature_id="FORM_PPG_DIFF", version=2,
    name="Разница очков за матч, окно 10",
    family="FORM", description="То же на окне 10 — для neighborhood-теста.",
    window=10, scope="ALL", season_transition="SEASON_RESET", minimum_history=10,
    compute=_make(10)))


def _gf_home_5(ctx, home: HistoryView, away: HistoryView):
    rec = [r for r in home.last(5) if r.gf is not None]
    return None if len(rec) < 5 else sum(r.gf for r in rec) / 5


GOALS_FOR_HOME_5 = REGISTRY.register(FeatureSpec(
    feature_id="GOALS_FOR_HOME", version=1,
    name="Средние забитые хозяев, окно 5",
    family="GOALS", description="Среднее забитых хозяевами за 5 прошлых матчей сезона.",
    window=5, scope="HOME_ONLY", season_transition="SEASON_RESET", minimum_history=5,
    compute=_gf_home_5))


def _rest_days_diff(ctx: PreMatchContext, home: HistoryView, away: HistoryView):
    """Разница в днях отдыха. Семейство REST/SCHEDULE."""
    if not len(home) or not len(away):
        return None
    h = (ctx.kickoff_utc - home.last(1)[0].kickoff_utc).total_seconds() / 86400
    a = (ctx.kickoff_utc - away.last(1)[0].kickoff_utc).total_seconds() / 86400
    return h - a


REST_DAYS_DIFF = REGISTRY.register(FeatureSpec(
    feature_id="REST_DAYS_DIFF", version=1,
    name="Разница дней отдыха",
    family="REST", description="Дни от предыдущего матча у хозяев минус у гостей.",
    window=1, scope="ALL", season_transition="SEASON_RESET", minimum_history=1,
    compute=_rest_days_diff))
