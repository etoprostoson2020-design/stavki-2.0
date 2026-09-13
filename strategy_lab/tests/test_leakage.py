"""Red Team #1: намеренная утечка обязана блокироваться."""
import datetime as dt

import pytest

from fsl.features.compute import compute_features
from fsl.features.registry import FeatureSpec, PreMatchContext
from fsl.temporal.time_machine import (HistoryView, LeakageError, MatchRecord,
                                       TimeMachine, leakage_regression_test)
from tests.conftest import fx


def test_premat_context_has_no_outcome():
    """Признак физически не может прочитать исход своего матча."""
    ctx = PreMatchContext(1, "ESP_1", "S1", dt.datetime.now(dt.timezone.utc),
                          "EXACT", 1, "A", "B")
    for forbidden in ("fthg", "ftag", "ftr", "stats", "hthg"):
        assert not hasattr(ctx, forbidden), f"в контексте оказалось поле {forbidden}"


def test_history_view_rejects_future_record():
    """Матч своего или будущего блока не может попасть в историю."""
    future = MatchRecord(9, "S1", 5, dt.datetime.now(dt.timezone.utc), "A", "B",
                         True, 1, 0, 3, {})
    with pytest.raises(LeakageError):
        HistoryView([future], boundary_batch=5, season="S1")


def test_same_batch_matches_do_not_see_each_other(tiny):
    """Матчи одного синхронного блока не видят результатов друг друга."""
    same = [fx(1, "S1", 1, "A", "B", 3, 0), fx(2, "S1", 1, "C", "A", 0, 0)]
    seen = {}
    for f, hv, av in TimeMachine(same).walk():
        seen[f["fixture_id"]] = (len(hv), len(av))
    assert seen == {1: (0, 0), 2: (0, 0)}


def test_future_leak_is_caught_by_regression_test(tiny):
    """Признак «итоговые очки команды за сезон» — классическая утечка из будущего.

    Документ 10, фаза 3: season-final-position обязан блокироваться.
    Регресс-тест ловит именно этот класс: значение прошлого матча меняется,
    когда портится будущее.
    """
    season_totals: dict[tuple[str, str], int] = {}

    def leaky_compute(fixtures):
        season_totals.clear()
        for f in fixtures:                      # смотрит ВЕСЬ сезон, включая будущее
            for team, gf, ga in ((f["home_team"], f["fthg"], f["ftag"]),
                                 (f["away_team"], f["ftag"], f["fthg"])):
                pts = 3 if gf > ga else 1 if gf == ga else 0
                season_totals[(f["season"], team)] = \
                    season_totals.get((f["season"], team), 0) + pts

        def final_points(ctx, home, away):
            return float(season_totals.get((ctx.season, ctx.home_team), 0))

        spec = FeatureSpec("SEASON_FINAL_POINTS", 1, "итоговые очки", "LEAGUE_STATE",
                           "", None, "ALL", "SEASON_RESET", 0, final_points)
        return compute_features(fixtures, [spec])

    bad = leakage_regression_test(tiny, leaky_compute, n_points=3, seed=1)
    assert not bad["clean"], "регресс-тест обязан был поймать утечку из будущего"
    assert bad["discrepancies"] > 0


def test_honest_feature_passes_regression_test(tiny):
    """Признак, читающий только прошлое, расхождений не даёт."""
    spec = FeatureSpec("HONEST_PPG", 1, "очки за 2 матча", "FORM", "", 2, "ALL",
                       "SEASON_RESET", 2,
                       lambda ctx, h, a: None if len(h) < 2 else
                       sum(r.points for r in h.last(2)) / 2)
    good = leakage_regression_test(
        tiny, lambda fixtures: compute_features(fixtures, [spec]), n_points=3, seed=1)
    assert good["clean"] and good["discrepancies"] == 0
