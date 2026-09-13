"""Фаза 6, приёмка по документу 10.

  - синтетический истинный паттерн обязан проходить;
  - паттерн, существующий только в discovery, обязан умирать или уходить в PARK;
  - случайный мир не должен массово давать ROBUST;
  - просмотренный период не может выдать ROBUST;
  - подмена критерия после заморозки обязана блокироваться.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from fsl.experiments.engine import Condition, run_experiment
from fsl.validation.engine import (HardFail, evaluate_oos, freeze_strategy,
                                   qualification_gate, run_robustness)
from fsl.validation.null_world import run_null_world
from fsl.validation.policy import Policy, qualification_policy, statistical_policy
from fsl.validation.search_batch import Candidate, build_matrices, z_scores

QUAL, STAT = qualification_policy(), statistical_policy()
KEY = "SYN.v1"


def synth(seasons, n_per_season, effect, *, base=0.45, seed=0, teams=20):
    """Датасет с управляемым эффектом: при feature >= 1.0 исход чаще на `effect`."""
    rng = np.random.default_rng(seed)
    fixtures, values, fid, batch = [], {}, 0, 0
    for season in seasons:
        for i in range(n_per_season):
            fid += 1
            batch += 1
            v = float(rng.uniform(-2, 2))
            p = base + (effect if v >= 1.0 else 0.0)
            home_win = rng.random() < p
            h, a = (2, 0) if home_win else (0, 1)
            fixtures.append({
                "fixture_id": fid, "league": "SYN", "season": season,
                "kickoff_utc": dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
                               + dt.timedelta(days=batch),
                "kickoff_precision": "EXACT", "sync_batch": batch,
                "home_team": f"T{i % teams}", "away_team": f"T{(i + 7) % teams}",
                "fthg": h, "ftag": a, "ftr": "H" if h > a else "A",
                "hthg": 0, "htag": 0, "stats": {}})
            values[fid] = {KEY: v}
    return fixtures, values


COND = [Condition(KEY, ">=", 1.0)]


def _discovery(fx, vals):
    return run_experiment(fx, vals, COND, "RES_HOME", hypothesis="syn",
                          dataset_version="dsv", feature_versions={KEY: "h"})


def _freeze(seen):
    return freeze_strategy("STR-SYN", 1, COND, "RES_HOME", {KEY: "h"}, "dsv",
                           seen_seasons=seen, qualification=QUAL, statistical=STAT)


def test_true_pattern_passes_on_genuinely_unseen_data():
    disc_fx, disc_v = synth(["S1", "S2", "S3"], 400, effect=0.20, seed=1)
    oos_fx, oos_v = synth(["S4", "S5"], 400, effect=0.20, seed=2)
    fz = _freeze(seen=["S1", "S2", "S3"])
    res = evaluate_oos(fz, _discovery(disc_fx, disc_v), oos_fx, oos_v,
                       oos_seasons=["S4", "S5"], unseen_at_freeze=["S4", "S5"],
                       qualification=QUAL, statistical=STAT)
    assert res["oos_validity"] == "VALID_OOS"
    assert res["outcome"] == "PASS"
    assert res["strategy_class"] == "ROBUST"
    assert res["action"] == "KEEP"


def test_discovery_only_pattern_does_not_survive():
    """Эффект есть в discovery и отсутствует в OOS -> ROBUST не выдаётся."""
    disc_fx, disc_v = synth(["S1", "S2", "S3"], 400, effect=0.20, seed=3)
    oos_fx, oos_v = synth(["S4", "S5"], 400, effect=0.0, seed=4)
    fz = _freeze(seen=["S1", "S2", "S3"])
    res = evaluate_oos(fz, _discovery(disc_fx, disc_v), oos_fx, oos_v,
                       oos_seasons=["S4", "S5"], unseen_at_freeze=["S4", "S5"],
                       qualification=QUAL, statistical=STAT)
    assert res["strategy_class"] != "ROBUST"
    assert res["outcome"] in ("FAIL", "INCONCLUSIVE")
    assert res["action"] in ("KILL", "PARK")


def test_seen_block_cannot_produce_robust():
    """Сильный результат на просмотренных данных всё равно не ROBUST."""
    disc_fx, disc_v = synth(["S1", "S2"], 400, effect=0.25, seed=5)
    oos_fx, oos_v = synth(["S3", "S4"], 400, effect=0.25, seed=6)
    fz = _freeze(seen=["S1", "S2", "S3", "S4"])          # OOS-блок уже просмотрен
    res = evaluate_oos(fz, _discovery(disc_fx, disc_v), oos_fx, oos_v,
                       oos_seasons=["S3", "S4"], unseen_at_freeze=[],
                       qualification=QUAL, statistical=STAT)
    assert res["outcome"] == "PASS"                      # критерий выполнен
    assert res["oos_validity"] == "REPLAY_OF_SEEN"
    assert res["strategy_class"] == "CANDIDATE"          # но ROBUST не присваивается
    assert any("просмотрен" in n for n in res["notes"])


def test_criterion_change_after_freeze_is_hard_fail():
    """Red Team #11: критерий нельзя переписать, увидев OOS-результат."""
    disc_fx, disc_v = synth(["S1", "S2"], 300, effect=0.15, seed=7)
    oos_fx, oos_v = synth(["S3"], 300, effect=0.02, seed=8)
    fz = _freeze(seen=["S1", "S2"])
    softened = Policy(QUAL.name, QUAL.version,
                      {**QUAL.payload, "oos_pass": {**QUAL.payload["oos_pass"],
                                                    "min_z": 0.1}})
    with pytest.raises(HardFail) as e:
        evaluate_oos(fz, _discovery(disc_fx, disc_v), oos_fx, oos_v,
                     oos_seasons=["S3"], unseen_at_freeze=["S3"],
                     qualification=softened, statistical=STAT)
    assert e.value.code == "CRITERION_CHANGED_AFTER_FREEZE"


def test_negative_effect_direction_is_handled():
    """Правило, предсказывающее исход РЕЖЕ обычного, оценивается по своему знаку."""
    disc_fx, disc_v = synth(["S1", "S2"], 400, effect=-0.20, seed=9)
    oos_fx, oos_v = synth(["S3", "S4"], 400, effect=-0.20, seed=10)
    disc = _discovery(disc_fx, disc_v)
    assert disc["absolute_uplift"] < 0 and disc["z"] < 0
    fz = _freeze(seen=["S1", "S2"])
    res = evaluate_oos(fz, disc, oos_fx, oos_v, oos_seasons=["S3", "S4"],
                       unseen_at_freeze=["S3", "S4"], qualification=QUAL,
                       statistical=STAT)
    assert res["direction"] == -1
    assert res["effective"]["oos_z"] > 0
    assert res["outcome"] == "PASS" and res["strategy_class"] == "ROBUST"


# ------------------------------------------------------------- null world
def _batch(fixtures, values, n_thresholds):
    cands = []
    for i, thr in enumerate(np.linspace(-1.5, 1.5, n_thresholds)):
        for t in ("RES_HOME", "RES_AWAY"):
            cands.append(Candidate(f"c{i}_{t}", (Condition(KEY, ">=", float(thr)),), t))
    return build_matrices(fixtures, values, cands)


def test_random_world_does_not_mass_produce_survivors():
    """Red Team #2: на случайном таргете порог батча почти никто не проходит."""
    fx, vals = synth(["S1", "S2", "S3"], 400, effect=0.0, seed=11)
    bm = _batch(fx, vals, 30)
    nw = run_null_world(bm, worlds=150, seed=3)
    z = np.abs(np.nan_to_num(z_scores(bm)))
    assert nw.n_negative_passing == 0
    assert int((z >= nw.fwer_threshold).sum()) <= 3, "случайный мир массово прошёл порог"


def test_threshold_grows_with_batch_size():
    """Порог значимости — функция размера батча, а не константа."""
    fx, vals = synth(["S1", "S2", "S3"], 400, effect=0.0, seed=12)
    small = run_null_world(_batch(fx, vals, 3), worlds=200, seed=5).fwer_threshold
    large = run_null_world(_batch(fx, vals, 60), worlds=200, seed=5).fwer_threshold
    assert large > small, f"порог не вырос: {small} -> {large}"


def test_qualification_gate_blocks_one_team_effect():
    """Red Team #4: эффект, собранный на одной команде, гейт не пропускает."""
    fx, vals = synth(["S1", "S2"], 300, effect=0.2, seed=13, teams=1)
    disc = _discovery(fx, vals)
    robust = run_robustness(fx, vals, COND, "RES_HOME")
    gate = qualification_gate(disc, robust, QUAL)
    assert not gate["passed"]
    assert "max_top5_team_share" in gate["failed"]


def test_passing_negative_control_fails_the_whole_batch():
    """Прошедший негативный контроль означает, что порогу батча верить нельзя."""
    import dataclasses as dc

    from fsl.validation.null_world import NullWorldResult

    disc_fx, disc_v = synth(["S1", "S2"], 300, effect=0.2, seed=14)
    oos_fx, oos_v = synth(["S3"], 300, effect=0.2, seed=15)
    fz = _freeze(seen=["S1", "S2"])
    tainted = NullWorldResult(method="circular_shift_within_season", worlds=300,
                              fwer_threshold=3.0, median_max_z=2.2, max_abs_z_real=8.0,
                              n_real_passing=5, n_negative_controls=40,
                              n_negative_passing=2, max_abs_z_negative=3.4,
                              percentile=95)
    with pytest.raises(HardFail) as e:
        evaluate_oos(fz, _discovery(disc_fx, disc_v), oos_fx, oos_v,
                     oos_seasons=["S3"], unseen_at_freeze=["S3"],
                     qualification=QUAL, statistical=STAT, null_result=tainted)
    assert e.value.code == "NEGATIVE_CONTROL_PASSED"
    assert dc.asdict(tainted)["n_negative_passing"] == 2
