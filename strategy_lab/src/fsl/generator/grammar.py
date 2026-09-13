"""Язык гипотез.

Документ 04: `CONTEXT + CONDITIONS + TARGET`. Генератор отвечает на вопрос
«что проверить», а не «что получилось» — оценивать он не имеет права.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Literal

from fsl.experiments.engine import Condition
from fsl.hashing import stable_hash
from fsl.memory.fingerprints import semantic_fingerprint

HypothesisType = Literal["SINGLE", "DIFFERENCE", "SUM", "INTERACTION", "SEQUENCE"]
Origin = Literal["RULE_GENERATOR", "MUTATION", "AI_RESEARCHER", "HUMAN", "TRANSFER",
                 "ANOMALY_DETECTION", "META_LEARNING", "REVIVED_PARKED_IDEA"]
Mode = Literal["SYSTEMATIC", "MUTATION", "TRANSFER", "EXPLORATION", "AI_PROPOSED", "REVIVAL"]

#: Классы признаков. Термины разведены сознательно: «team-blind» в документе 04
#: и «TEAM_BLIND» в коде v4 означали разное.
FeatureClass = Literal["TEAM_RELATIVE", "TEAM_SPECIFIC", "LEAGUE_STATE"]


@dc.dataclass(frozen=True)
class Hypothesis:
    """Гипотеза, а не стратегия. Статус ей присваивает Validation Engine."""
    hypothesis_key: str
    conditions: tuple[Condition, ...]
    target: str
    htype: HypothesisType
    origin: Origin
    mode: Mode
    family: str
    league: str
    seasons: tuple[str, ...]
    complexity: int
    generation: int = 0
    parent_key: str | None = None
    mutation_reason: str | None = None
    context_filters: tuple[str, ...] = ()

    @property
    def semantic(self) -> str:
        return semantic_fingerprint(list(self.conditions), self.target)

    @property
    def fingerprint(self) -> str:
        return stable_hash({
            "conditions": sorted(c.as_dict() for c in self.conditions),
            "target": self.target, "context": sorted(self.context_filters)})

    def as_dict(self) -> dict:
        return {"hypothesis_key": self.hypothesis_key, "type": self.htype,
                "origin": self.origin, "mode": self.mode, "family": self.family,
                "target": self.target, "complexity": self.complexity,
                "generation": self.generation, "parent_key": self.parent_key,
                "mutation_reason": self.mutation_reason,
                "conditions": [c.as_dict() for c in self.conditions],
                "context_filters": list(self.context_filters),
                "fingerprint": self.fingerprint, "semantic": self.semantic}


def complexity_of(conditions, context_filters=()) -> int:
    """Простое предпочтительнее сложного при близком результате (документ 01).

    Считаем: одно очко за условие, одно за каждое лишнее семейство признаков,
    одно за каждый контекстный фильтр.
    """
    fams = {c.feature_key.split(".")[0] for c in conditions}
    return len(conditions) + max(len(fams) - 1, 0) + len(context_filters)


def type_of(conditions) -> HypothesisType:
    if len(conditions) == 1:
        key = conditions[0].feature_key
        if "DIFF" in key.upper():
            return "DIFFERENCE"
        if "SUM" in key.upper():
            return "SUM"
        return "SINGLE"
    return "INTERACTION"


def feature_class(feature_key: str) -> FeatureClass:
    """Классификация признака для team-политики."""
    head = feature_key.split(".")[0].upper()
    if head.startswith(("L_", "LEAGUE", "PB_")):
        return "LEAGUE_STATE"
    return "TEAM_RELATIVE"          # скользящее окно команды, а не имя клуба


def make_key(conditions, target: str, context_filters=()) -> str:
    parts = "&".join(f"{c.feature_key}{c.op}{c.threshold}"
                     for c in sorted(conditions, key=lambda x: x.feature_key))
    ctx = ("|" + ",".join(sorted(context_filters))) if context_filters else ""
    return f"{parts}->{target}{ctx}"
