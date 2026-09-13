"""Experiment Engine. Считает результат гипотезы воспроизводимо.

Не решает, работает ли стратегия — это дело Validation Engine (фаза 6).
"""
from __future__ import annotations

import dataclasses as dc
import math
from collections import Counter
from typing import Callable

from fsl.hashing import canonical, environment_lock, stable_hash
from fsl.logging import get_logger

log = get_logger(__name__)

POLICY_VERSION = "STATISTICAL_POLICY_v0.1"

#: Каталог таргетов MVP (документ 04). Каждый — функция от завершённого матча.
TARGETS: dict[str, Callable[[dict], int | None]] = {
    "RES_HOME": lambda f: None if f["ftr"] is None else int(f["ftr"] == "H"),
    "RES_DRAW": lambda f: None if f["ftr"] is None else int(f["ftr"] == "D"),
    "RES_AWAY": lambda f: None if f["ftr"] is None else int(f["ftr"] == "A"),
    "OVER_25": lambda f: None if f["fthg"] is None or f["ftag"] is None
                         else int(f["fthg"] + f["ftag"] > 2.5),
    "BTTS_YES": lambda f: None if f["fthg"] is None or f["ftag"] is None
                          else int(f["fthg"] > 0 and f["ftag"] > 0),
    "FH_GOAL": lambda f: None if f["hthg"] is None or f["htag"] is None
                         else int(f["hthg"] + f["htag"] > 0),
}


@dc.dataclass(frozen=True)
class Condition:
    feature_key: str
    op: str            # ">=" | "<="
    threshold: float

    def holds(self, value: float | None) -> bool | None:
        if value is None:
            return None                     # NOT_ELIGIBLE, а не проигрыш
        return value >= self.threshold if self.op == ">=" else value <= self.threshold

    def as_dict(self) -> dict:
        return {"feature": self.feature_key, "op": self.op, "threshold": self.threshold}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (centre - half, centre + half)


def run_experiment(fixtures: list[dict],
                   feature_values: dict[int, dict[str, float | None]],
                   conditions: list[Condition], target: str, *,
                   hypothesis: str, dataset_version: str,
                   feature_versions: dict[str, str]) -> dict:
    """Считает один эксперимент. Одинаковые входы обязаны дать одинаковый result_hash."""
    if target not in TARGETS:
        raise ValueError(f"таргет {target} нет в каталоге; доступны {sorted(TARGETS)}")
    tf = TARGETS[target]

    eligible, signals = [], []
    for f in fixtures:
        y = tf(f)
        if y is None:
            continue                                   # исход неизвестен
        vals = feature_values.get(f["fixture_id"], {})
        verdicts = [c.holds(vals.get(c.feature_key)) for c in conditions]
        if any(v is None for v in verdicts):
            continue                                   # NOT_ELIGIBLE: нет истории
        eligible.append((f, y))
        if all(verdicts):
            signals.append((f, y))

    n_elig, n_sig = len(eligible), len(signals)
    if n_sig == 0:
        raise RuntimeError("гипотеза не дала ни одного сигнала")

    baseline = sum(y for _, y in eligible) / n_elig
    successes = sum(y for _, y in signals)
    hit = successes / n_sig
    z = ((hit - baseline) / math.sqrt(baseline * (1 - baseline) / n_sig)
         if 0 < baseline < 1 else float("nan"))
    lo, hi = wilson(successes, n_sig)

    per_season = {}
    for season in sorted({f["season"] for f, _ in eligible}):
        se = [(f, y) for f, y in eligible if f["season"] == season]
        ss = [(f, y) for f, y in signals if f["season"] == season]
        per_season[season] = {
            "n_eligible": len(se), "n_signals": len(ss),
            "baseline": (sum(y for _, y in se) / len(se)) if se else None,
            "hit_rate": (sum(y for _, y in ss) / len(ss)) if ss else None,
        }
        b, h = per_season[season]["baseline"], per_season[season]["hit_rate"]
        per_season[season]["uplift"] = None if b is None or h is None else h - b

    team_counts = Counter()
    for f, _ in signals:
        team_counts[f["home_team"]] += 1
        team_counts[f["away_team"]] += 1
    top = team_counts.most_common(5)
    concentration = {
        "distinct_teams": len(team_counts),
        "top5_share": round(sum(c for _, c in top) / (2 * n_sig), 4) if n_sig else None,
        "top5": [{"team": t, "signals": c} for t, c in top],
    }

    core = {
        "hypothesis": hypothesis,
        "conditions": [c.as_dict() for c in conditions],
        "target": target,
        "seasons": sorted({f["season"] for f in fixtures}),
        "league": fixtures[0]["league"],
        "n_eligible": n_elig, "n_signals": n_sig, "n_successes": successes,
        "signal_frequency": n_sig / n_elig,
        "baseline": baseline, "hit_rate": hit,
        "absolute_uplift": hit - baseline,
        "relative_uplift": hit / baseline if baseline else None,
        "ci95_low": lo, "ci95_high": hi, "z": z,
        "per_season": per_season,
        "per_team_concentration": concentration,
        "dataset_version": dataset_version,
        "feature_versions": feature_versions,
        "environment_lock": environment_lock(),
        "policy_version": POLICY_VERSION,
    }
    # хэш считается от канонизированных значений: устойчив к дрейфу float
    core["result_hash"] = stable_hash(canonical(core))
    core["experiment_id"] = "EXP-" + core["result_hash"][:12]
    log.info("experiment.done", experiment_id=core["experiment_id"],
             n=n_sig, uplift=round(core["absolute_uplift"], 4),
             result_hash=core["result_hash"])
    return core
