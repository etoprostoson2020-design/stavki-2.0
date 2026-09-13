"""Validation Engine.

Разделение по документу 05: Experiment Engine считает результат, Validation
Engine решает, чего он стоит.

Два правила, которых в архитектурном пакете не было и которые здесь встроены
в код, а не в инструкцию:

1. **Критерий замораживается вместе с формулой.** В заморозку входит хэш
   QUALIFICATION_POLICY. Если критерий изменили после того, как OOS-результат
   увиден, сверка хэша даёт HARD FAIL. Это Red Team #11.
2. **Просмотренный период не может выдать ROBUST.** Документ 01 запрещает
   переиспользовать seen-данные как OOS. Движок проверяет это по Holdout
   Ledger и понижает вердикт до REPLAY_OF_SEEN, каким бы сильным ни был z.
"""
from __future__ import annotations

import dataclasses as dc
import datetime as dt
from typing import Literal

from fsl.experiments.engine import Condition, run_experiment
from fsl.hashing import stable_hash
from fsl.logging import get_logger
from fsl.validation import robustness as rb
from fsl.validation.policy import Policy

log = get_logger(__name__)

#: Версия движка. Входит в запись прогона: результаты, посчитанные разными
#: версиями, несопоставимы, и по таблице это должно быть видно.
ENGINE_VERSION = "VALIDATION_ENGINE_v0.2"

Outcome = Literal["PASS", "WEAK_PASS", "INCONCLUSIVE", "FAIL"]
Action = Literal["KEEP", "MUTATE", "PARK", "KILL"]
StrategyClass = Literal["REJECTED", "CANDIDATE", "ROBUST", "STRUCTURAL_MECHANISM"]

#: Провалы, которые блокируют продвижение независимо от величины эффекта.
HARD_FAILS = ("LEAKAGE", "BROKEN_CHRONOLOGY", "AMBIGUOUS_TARGET", "CORRUPTED_DATA",
              "UNREPRODUCIBLE", "CRITICAL_MISSINGNESS", "FORMULA_MISMATCH",
              "CRITERION_CHANGED_AFTER_FREEZE", "NEGATIVE_CONTROL_PASSED")


class HardFail(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        if code not in HARD_FAILS:
            raise ValueError(f"неизвестный код hard fail: {code}")
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


@dc.dataclass(frozen=True)
class StrategyFreeze:
    """Immutable снимок перед OOS. Любое изменение — новая версия."""
    strategy_id: str
    version: int
    conditions: tuple[Condition, ...]
    target: str
    feature_versions: dict[str, str]
    dataset_version: str
    seen_seasons: tuple[str, ...]
    qualification_policy_hash: str
    statistical_policy_hash: str
    frozen_at: str

    @property
    def formula_hash(self) -> str:
        return stable_hash({"conditions": [c.as_dict() for c in self.conditions],
                            "target": self.target,
                            "feature_versions": self.feature_versions})

    @property
    def strategy_hash(self) -> str:
        return stable_hash({
            "strategy_id": self.strategy_id, "version": self.version,
            "formula": self.formula_hash, "dataset_version": self.dataset_version,
            "seen_seasons": sorted(self.seen_seasons),
            "qualification_policy": self.qualification_policy_hash,
            "statistical_policy": self.statistical_policy_hash})

    def as_dict(self) -> dict:
        return {"strategy_id": self.strategy_id, "version": self.version,
                "conditions": [c.as_dict() for c in self.conditions],
                "target": self.target, "feature_versions": self.feature_versions,
                "dataset_version": self.dataset_version,
                "seen_seasons": sorted(self.seen_seasons),
                "qualification_policy_hash": self.qualification_policy_hash,
                "statistical_policy_hash": self.statistical_policy_hash,
                "frozen_at": self.frozen_at, "formula_hash": self.formula_hash,
                "strategy_hash": self.strategy_hash}


def freeze_strategy(strategy_id: str, version: int, conditions: list[Condition],
                    target: str, feature_versions: dict[str, str],
                    dataset_version: str, seen_seasons: list[str],
                    qualification: Policy, statistical: Policy) -> StrategyFreeze:
    return StrategyFreeze(
        strategy_id=strategy_id, version=version, conditions=tuple(conditions),
        target=target, feature_versions=dict(feature_versions),
        dataset_version=dataset_version, seen_seasons=tuple(sorted(seen_seasons)),
        qualification_policy_hash=qualification.hash,
        statistical_policy_hash=statistical.hash,
        frozen_at=dt.datetime.now(dt.timezone.utc).isoformat())


# ------------------------------------------------------ Qualification Gate
def qualification_gate(discovery: dict, robust: dict, qualification: Policy) -> dict:
    """Пускать ли гипотезу в валидацию. In-sample результат доказательством не является."""
    g = qualification.get("candidate_gate", default={})
    checks = {
        "min_signals": (discovery["n_signals"] >= g.get("min_signals", 0),
                        discovery["n_signals"], g.get("min_signals")),
        "min_signal_frequency": (discovery["signal_frequency"] >= g.get("min_signal_frequency", 0),
                                 round(discovery["signal_frequency"], 4),
                                 g.get("min_signal_frequency")),
        "max_top5_team_share": (
            (robust["team_concentration"]["top5_share"] or 0) <= g.get("max_top5_team_share", 1),
            robust["team_concentration"]["top5_share"], g.get("max_top5_team_share")),
        "min_seasons_with_signals": (
            sum(1 for v in robust["season_breakdown"].values() if v["n_signals"] > 0)
            >= g.get("min_seasons_with_signals", 0),
            sum(1 for v in robust["season_breakdown"].values() if v["n_signals"] > 0),
            g.get("min_seasons_with_signals")),
    }
    passed = all(v[0] for v in checks.values())
    return {"passed": passed,
            "checks": {k: {"ok": v[0], "value": v[1], "required": v[2]}
                       for k, v in checks.items()},
            "failed": [k for k, v in checks.items() if not v[0]]}


def run_robustness(fixtures, feature_values, conditions, target,
                   window_alternatives: dict[str, str] | None = None) -> dict:
    return {
        "walk_forward": rb.walk_forward(fixtures, feature_values, conditions, target),
        "season_breakdown": rb.season_breakdown(fixtures, feature_values, conditions, target),
        "team_concentration": rb.team_concentration(fixtures, feature_values, conditions, target),
        "leave_one_team_out": rb.leave_one_team_out(fixtures, feature_values, conditions, target),
        "parameter_neighborhood": rb.parameter_neighborhood(fixtures, feature_values,
                                                            conditions, target),
        "window_neighborhood": (rb.window_neighborhood(fixtures, feature_values, conditions,
                                                       target, window_alternatives)
                                if window_alternatives else {"supported": False}),
        "temporal_clustering": rb.temporal_clustering(fixtures, feature_values, conditions, target),
        "missingness_bias": rb.missingness_bias(fixtures, feature_values, conditions, target),
    }


# ------------------------------------------------------------------- OOS
def evaluate_oos(freeze: StrategyFreeze, discovery: dict, oos_fixtures: list[dict],
                 oos_feature_values: dict, *, oos_seasons: list[str],
                 unseen_at_freeze: list[str], qualification: Policy,
                 statistical: Policy, null_result=None) -> dict:
    """Считает OOS по замороженному правилу и выносит вердикт."""
    # --- Red Team #11: критерий не мог измениться после заморозки -----------
    if qualification.hash != freeze.qualification_policy_hash:
        raise HardFail("CRITERION_CHANGED_AFTER_FREEZE",
                       f"в заморозке {freeze.qualification_policy_hash}, "
                       f"сейчас {qualification.hash}")
    if statistical.hash != freeze.statistical_policy_hash:
        raise HardFail("CRITERION_CHANGED_AFTER_FREEZE",
                       "STATISTICAL_POLICY изменилась после заморозки")

    # --- негативный контроль прошёл порог => батч недостоверен целиком ------
    if null_result is not None and null_result.n_negative_passing > 0:
        raise HardFail("NEGATIVE_CONTROL_PASSED",
                       f"{null_result.n_negative_passing} контролей выше порога "
                       f"{null_result.fwer_threshold}")

    oos = run_experiment(oos_fixtures, oos_feature_values, list(freeze.conditions),
                         freeze.target, hypothesis=f"OOS {freeze.strategy_id}",
                         dataset_version=freeze.dataset_version,
                         feature_versions=freeze.feature_versions)

    # --- просмотренный период не может служить OOS --------------------------
    replay = sorted(set(oos_seasons) - set(unseen_at_freeze))
    oos_validity = "VALID_OOS" if not replay else "REPLAY_OF_SEEN"

    p = qualification.get("oos_pass", default={})
    lab_up, oos_up = discovery["absolute_uplift"], oos["absolute_uplift"]
    per_season = oos["per_season"]

    # Направление эффекта. Правило вида «признак ниже порога -> исход РЕЖЕ
    # обычного» — такая же стратегия, как обратная ей, просто предсказывает
    # отрицание таргета. Критерий обязан считаться на одной основе с uplift,
    # иначе сильный отрицательный эффект провалится по знаку z.
    direction = 1.0 if lab_up >= 0 else -1.0
    lab_eff = direction * lab_up          # всегда >= 0
    oos_eff = direction * oos_up
    z_eff = direction * oos["z"]
    season_eff = {k: (None if v["uplift"] is None else direction * v["uplift"])
                  for k, v in per_season.items()}

    conds = {
        "sign_matches_lab": (not p.get("sign_must_match_lab", True)) or oos_eff > 0,
        "uplift_fraction": oos_eff >= p.get("min_fraction_of_lab_uplift", 0.5) * lab_eff,
        "min_z": z_eff >= p.get("min_z", 2.0),
        "sign_every_season": (not p.get("sign_must_hold_in_every_season", True))
                             or all(v is not None and v > 0 for v in season_eff.values()),
    }
    n_ok = sum(conds.values())
    if n_ok == len(conds):
        outcome: Outcome = "PASS"
    elif n_ok >= len(conds) - 1 and conds["sign_matches_lab"] and conds["min_z"]:
        outcome = "WEAK_PASS"
    elif conds["sign_matches_lab"]:
        outcome = "INCONCLUSIVE"
    else:
        outcome = "FAIL"

    action: Action = {"PASS": "KEEP", "WEAK_PASS": "KEEP",
                      "INCONCLUSIVE": "PARK", "FAIL": "KILL"}[outcome]

    if outcome == "PASS" and oos_validity == "VALID_OOS":
        klass: StrategyClass = "ROBUST"
    elif outcome in ("PASS", "WEAK_PASS"):
        klass = "CANDIDATE"
    elif outcome == "INCONCLUSIVE":
        klass = "CANDIDATE"
    else:
        klass = "REJECTED"

    notes = []
    if oos_validity == "REPLAY_OF_SEEN":
        notes.append(f"сезоны {replay} были просмотрены до заморозки: "
                     f"это повтор на seen-данных, а не независимый OOS. "
                     f"ROBUST по такому прогону не присваивается.")
    if null_result is not None and abs(z_eff) < null_result.fwer_threshold:
        notes.append(f"|z|={abs(z_eff):.2f} ниже порога батча "
                     f"{null_result.fwer_threshold}: на фоне всего поиска "
                     f"результат неотличим от нулевого мира.")

    return {
        "strategy_id": freeze.strategy_id, "version": freeze.version,
        "strategy_hash": freeze.strategy_hash, "formula_hash": freeze.formula_hash,
        "oos_seasons": sorted(oos_seasons), "oos_validity": oos_validity,
        "replayed_seasons": replay,
        "discovery": {k: discovery[k] for k in
                      ("n_signals", "baseline", "hit_rate", "absolute_uplift", "z")},
        "oos": {k: oos[k] for k in
                ("n_eligible", "n_signals", "signal_frequency", "baseline", "hit_rate",
                 "absolute_uplift", "relative_uplift", "z", "ci95_low", "ci95_high",
                 "per_season")},
        "criterion": {k: bool(v) for k, v in conds.items()},
        "direction": int(direction),
        "effective": {"lab_uplift": round(lab_eff, 4), "oos_uplift": round(oos_eff, 4),
                      "oos_z": round(z_eff, 2),
                      "per_season_uplift": {k: (None if v is None else round(v, 4))
                                            for k, v in season_eff.items()}},
        "criterion_source": {"policy": "QUALIFICATION_POLICY",
                             "hash": freeze.qualification_policy_hash,
                             "frozen_before_oos": True},
        "fwer_threshold": None if null_result is None else null_result.fwer_threshold,
        "engine_version": ENGINE_VERSION,
        "outcome": outcome, "action": action, "strategy_class": klass,
        "notes": notes,
    }


def structural_mechanism_gate(transfer_results: list[dict]) -> dict:
    """Высшая ступень. В пакете уровень объявлен, но критерия не имел.

    Здесь критерий задан явно: чистый перенос без мутации формулы, PASS
    минимум в двух лигах помимо исходной.
    """
    passing = [t for t in transfer_results
               if t.get("outcome") == "PASS" and t.get("formula_mutated") is False]
    leagues = {t["league"] for t in passing}
    return {"eligible": len(leagues) >= 2, "confirmed_leagues": sorted(leagues),
            "required": 2,
            "reason": None if len(leagues) >= 2 else
                      "нужен чистый перенос с PASS минимум в двух других лигах"}
