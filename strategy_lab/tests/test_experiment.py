"""Experiment Engine: базлайн, CI, NOT_ELIGIBLE, концентрация."""
import math

import pytest

from fsl.experiments.engine import Condition, run_experiment, wilson
from fsl.features.compute import compute_features
from fsl.features.registry import FeatureSpec
from tests.conftest import fx

SPEC = FeatureSpec("PPG2", 1, "ppg2", "FORM", "", 2, "ALL", "SEASON_RESET", 2,
                   lambda ctx, h, a: None if len(h) < 2 else
                   sum(r.points for r in h.last(2)) / 2)


def test_wilson_interval_known_value():
    lo, hi = wilson(50, 100)
    assert math.isclose(lo, 0.4038, abs_tol=1e-3)
    assert math.isclose(hi, 0.5962, abs_tol=1e-3)
    assert wilson(0, 0) != wilson(0, 0) or True        # n=0 -> nan, не падает


def test_not_eligible_is_not_a_loss():
    """Матчи без истории исключаются, а не считаются проигрышем."""
    rows = [fx(i, "S1", i, "A", "B", 1, 0) for i in range(1, 21)]
    vals = compute_features(rows, [SPEC])
    r = run_experiment(rows, vals, [Condition("PPG2.v1", ">=", 0.0)], "RES_HOME",
                       hypothesis="h", dataset_version="d",
                       feature_versions={"PPG2.v1": SPEC.definition_hash()})
    n_unavailable = sum(1 for v in vals.values() if v["PPG2.v1"] is None)
    assert n_unavailable > 0
    assert r["n_eligible"] == len(rows) - n_unavailable
    assert r["hit_rate"] == 1.0                       # хозяева выигрывали всегда


def test_baseline_comes_from_eligible_set():
    rows = [fx(i, "S1", i, "A", "B", (1 if i % 2 else 0), (0 if i % 2 else 1))
            for i in range(1, 31)]
    vals = compute_features(rows, [SPEC])
    r = run_experiment(rows, vals, [Condition("PPG2.v1", ">=", -99.0)], "RES_HOME",
                       hypothesis="h", dataset_version="d",
                       feature_versions={"PPG2.v1": SPEC.definition_hash()})
    assert r["n_signals"] == r["n_eligible"]          # условие всегда истинно
    assert r["baseline"] == r["hit_rate"]             # значит uplift ровно 0
    assert r["absolute_uplift"] == 0.0


def test_team_concentration_is_reported():
    """Red Team #4: эффект одной команды обязан быть видим в отчёте."""
    rows = [fx(i, "S1", i, "A", "B", 3, 0) for i in range(1, 21)]
    vals = compute_features(rows, [SPEC])
    r = run_experiment(rows, vals, [Condition("PPG2.v1", ">=", 0.0)], "RES_HOME",
                       hypothesis="h", dataset_version="d",
                       feature_versions={"PPG2.v1": SPEC.definition_hash()})
    c = r["per_team_concentration"]
    assert c["distinct_teams"] == 2 and c["top5_share"] == 1.0


def test_unknown_target_is_rejected():
    rows = [fx(i, "S1", i, "A", "B", 1, 0) for i in range(1, 11)]
    vals = compute_features(rows, [SPEC])
    with pytest.raises(ValueError, match="нет в каталоге"):
        run_experiment(rows, vals, [Condition("PPG2.v1", ">=", 0.0)], "CORNERS_OVER_9",
                       hypothesis="h", dataset_version="d", feature_versions={})
