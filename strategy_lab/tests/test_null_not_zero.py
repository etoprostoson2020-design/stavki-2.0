"""Red Team #7: NULL никогда не превращается в 0."""
from fsl.features.catalogue import FORM_PPG_DIFF_5, GOALS_FOR_HOME_5
from fsl.features.compute import compute_features
from tests.conftest import fx


def test_insufficient_history_is_unavailable_not_zero(tiny):
    vals = compute_features(tiny, [FORM_PPG_DIFF_5])
    first = vals[1]["FORM_PPG_DIFF.v1"]
    assert first is None, "при пустой истории должно быть UNAVAILABLE, а не 0"
    assert first != 0


def test_missing_source_stat_is_unavailable_not_zero():
    """Пропуск в источнике не подменяется нулём."""
    rows = [fx(i, "S1", i, "A", f"T{i}", 1, 0,
               stats={"HS": None, "AS": 8, "HST": 4, "AST": 3, "HF": 12, "AF": 11,
                      "HC": 5, "AC": 4, "HY": 2, "AY": 2, "HR": 0, "AR": 0})
            for i in range(1, 8)]
    from fsl.features.registry import FeatureSpec
    from fsl.temporal.time_machine import HistoryView

    def avg_hs(ctx, home: HistoryView, away):
        vals = [r.stats.get("HS") for r in home.last(3)]
        if len(vals) < 3 or any(v is None for v in vals):
            return None
        return sum(vals) / 3

    spec = FeatureSpec("AVG_HS", 1, "средние удары", "SHOTS", "", 3, "HOME_ONLY",
                       "SEASON_RESET", 3, avg_hs)
    vals = compute_features(rows, [spec])
    assert vals[7]["AVG_HS.v1"] is None


def test_season_reset_clears_window():
    """Окна обнуляются в межсезонье: SEASON_RESET, а не сквозной прокат."""
    rows = [fx(i, "S1", i, "A", f"T{i}", 3, 0) for i in range(1, 7)]
    rows += [fx(i, "S2", i, "A", f"T{i}", 3, 0) for i in range(7, 9)]
    vals = compute_features(rows, [GOALS_FOR_HOME_5])
    assert vals[6]["GOALS_FOR_HOME.v1"] == 3.0        # конец S1: история набрана
    assert vals[7]["GOALS_FOR_HOME.v1"] is None       # начало S2: счётчики обнулены
    assert vals[8]["GOALS_FOR_HOME.v1"] is None
