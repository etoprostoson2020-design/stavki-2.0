"""Дедупликация: exact, near, semantic и signal.

Red Team #8: поток одинаковых гипотез не должен превращаться в поток
«открытий». Проверка идёт ДО эксперимента, а не после.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Literal

from sqlalchemy import select

from fsl.memory import registry as reg
from fsl.memory.fingerprints import jaccard
from fsl.models import StrategySignalSet

Verdict = Literal["NEW", "EXACT_DUPLICATE", "SEMANTIC_KNOWN", "SIGNAL_DUPLICATE",
                  "NEAR_DUPLICATE", "RERUN_ON_NEW_DATA"]

NEAR_JACCARD = 0.90


@dc.dataclass
class DedupeResult:
    verdict: Verdict
    detail: str
    known_hypothesis_id: str | None = None
    jaccard: float | None = None

    @property
    def should_evaluate(self) -> bool:
        """Считать заново стоит только по-настоящему новое или на новых данных."""
        return self.verdict in ("NEW", "RERUN_ON_NEW_DATA", "SEMANTIC_KNOWN")

    def as_dict(self) -> dict:
        return dc.asdict(self) | {"should_evaluate": self.should_evaluate}


def check(sess, conditions, target, *, dataset_version: str, feature_versions: dict,
          policy_hashes: dict, signal_fixture_ids: list[int] | None = None
          ) -> DedupeResult:
    hit = reg.find_exact(sess, conditions, target, dataset_version, feature_versions,
                         policy_hashes)
    if hit is not None:
        return DedupeResult("EXACT_DUPLICATE",
                            f"проверялось {hit.times_seen} раз, "
                            f"z={hit.z}, статус {hit.status}", hit.hypothesis_id)

    # тот же вопрос, но данные другие -> это продолжение, а не дубликат
    same_logic = reg.find_similar(sess, conditions, target)
    for r in same_logic:
        if r.dataset_version != dataset_version and _same_formula(r, conditions):
            return DedupeResult("RERUN_ON_NEW_DATA",
                                f"та же формула на другом датасете "
                                f"({r.dataset_version} -> {dataset_version})",
                                r.hypothesis_id)

    if signal_fixture_ids:
        by_signal = reg.find_by_signal(sess, signal_fixture_ids)
        if by_signal:
            return DedupeResult("SIGNAL_DUPLICATE",
                                "другая формула отбирает ровно те же матчи",
                                by_signal[0].hypothesis_id, jaccard=1.0)
        near = _nearest_strategy(sess, set(signal_fixture_ids))
        if near and near[1] >= NEAR_JACCARD:
            return DedupeResult("NEAR_DUPLICATE",
                                f"пересечение сигналов с {near[0]} = {near[1]:.2f}",
                                near[0], jaccard=round(near[1], 3))

    if same_logic:
        best = max((abs(r.z) for r in same_logic if r.z is not None), default=None)
        return DedupeResult("SEMANTIC_KNOWN",
                            f"область уже исследовалась: {len(same_logic)} гипотез, "
                            f"лучший |z| {best}", same_logic[0].hypothesis_id)

    return DedupeResult("NEW", "в памяти не найдено")


def _same_formula(rec, conditions) -> bool:
    a = sorted((c["feature"], c["op"], round(float(c["threshold"]), 6))
               for c in rec.conditions)
    b = sorted((c.as_dict()["feature"], c.as_dict()["op"],
                round(float(c.as_dict()["threshold"]), 6)) for c in conditions)
    return a == b


def _nearest_strategy(sess, signals: set[int]):
    best = None
    for row in sess.scalars(select(StrategySignalSet)).all():
        j = jaccard(signals, set(row.fixture_ids))
        if best is None or j > best[1]:
            best = (f"{row.strategy_id}.v{row.version}", j)
    return best
