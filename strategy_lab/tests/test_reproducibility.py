"""Фаза 5: одинаковые входы -> одинаковый result_hash."""
from fsl.experiments.engine import Condition, run_experiment
from fsl.features.compute import compute_features
from fsl.features.registry import FeatureSpec
from fsl.hashing import canonical, stable_hash
from tests.conftest import fx

SPEC = FeatureSpec("PPG2", 1, "ppg2", "FORM", "", 2, "ALL", "SEASON_RESET", 2,
                   lambda ctx, h, a: None if len(h) < 2 else
                   sum(r.points for r in h.last(2)) / 2)


def _dataset():
    rows = []
    for i in range(1, 41):
        home, away = ("A", "B") if i % 2 else ("B", "A")
        rows.append(fx(i, "S1", i, home, away, 2 if i % 3 else 0, 1))
    return rows


def _run(rows):
    vals = compute_features(rows, [SPEC])
    return run_experiment(rows, vals, [Condition("PPG2.v1", ">=", 1.5)], "RES_HOME",
                          hypothesis="h", dataset_version="dsv-test",
                          feature_versions={"PPG2.v1": SPEC.definition_hash()})


def test_same_inputs_same_hash():
    assert _run(_dataset())["result_hash"] == _run(_dataset())["result_hash"]


def test_float_drift_does_not_change_hash():
    """0.1+0.2 и 0.3 обязаны хэшироваться одинаково."""
    assert stable_hash({"v": 0.1 + 0.2}) == stable_hash({"v": 0.3})
    assert canonical(float("nan")) == "NaN"


def test_changed_threshold_changes_hash():
    rows = _dataset()
    vals = compute_features(rows, [SPEC])
    kw = dict(hypothesis="h", dataset_version="dsv-test",
              feature_versions={"PPG2.v1": SPEC.definition_hash()})
    a = run_experiment(rows, vals, [Condition("PPG2.v1", ">=", 1.5)], "RES_HOME", **kw)
    b = run_experiment(rows, vals, [Condition("PPG2.v1", ">=", 2.0)], "RES_HOME", **kw)
    assert a["result_hash"] != b["result_hash"]


def test_environment_lock_is_part_of_result():
    r = _run(_dataset())
    assert set(r["environment_lock"]) >= {"numpy", "pandas", "scipy"}
