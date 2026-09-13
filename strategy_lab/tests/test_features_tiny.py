"""Фаза 4: признаки на крошечном датасете, посчитанном на бумаге."""
from fsl.features.catalogue import FORM_PPG_DIFF_5, GOALS_FOR_HOME_5
from fsl.features.compute import compute_features
from tests.conftest import fx


def test_goals_for_home_hand_calculated(tiny):
    """A забивает 2,1,3,0,0 в первых пяти матчах -> среднее перед шестым = 1.2."""
    vals = compute_features(tiny, [GOALS_FOR_HOME_5])
    assert vals[6]["GOALS_FOR_HOME.v1"] == (2 + 1 + 3 + 0 + 0) / 5 == 1.2
    assert vals[5]["GOALS_FOR_HOME.v1"] is None      # перед пятым истории лишь 4


def test_ppg_diff_hand_calculated():
    """A: 3 победы = 9 очков за 3 матча. B: 3 поражения = 0. Разница 3.0 - 0.0."""
    rows = [fx(1, "S1", 1, "A", "X", 1, 0), fx(2, "S1", 2, "A", "Y", 1, 0),
            fx(3, "S1", 3, "A", "Z", 1, 0),
            fx(4, "S1", 4, "B", "X", 0, 1), fx(5, "S1", 5, "B", "Y", 0, 1),
            fx(6, "S1", 6, "B", "Z", 0, 1),
            fx(7, "S1", 7, "A", "B", 0, 0)]
    from fsl.features.registry import FeatureSpec, PreMatchContext
    from fsl.temporal.time_machine import HistoryView

    def ppg3(ctx, home: HistoryView, away: HistoryView):
        h = [r.points for r in home.last(3)]
        a = [r.points for r in away.last(3)]
        if len(h) < 3 or len(a) < 3:
            return None
        return sum(h) / 3 - sum(a) / 3

    spec = FeatureSpec("PPG3", 1, "ppg3", "FORM", "", 3, "ALL", "SEASON_RESET", 3, ppg3)
    vals = compute_features(rows, [spec])
    assert vals[7]["PPG3.v1"] == 3.0


def test_window_neighborhood_differs(tiny):
    """Разные окна дают разное покрытие: окно 10 недоступно там, где 5 уже есть."""
    vals = compute_features(tiny, [FORM_PPG_DIFF_5])
    assert all(v["FORM_PPG_DIFF.v1"] is None for v in vals.values())  # соперники разные
