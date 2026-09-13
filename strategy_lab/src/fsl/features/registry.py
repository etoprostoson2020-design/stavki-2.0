"""Feature Registry по документу 03.

Ключевое решение: функция признака получает `PreMatchContext`, в котором нет
ни счёта, ни статистики своего матча. Признак не «не должен» читать свой исход —
ему нечем его прочитать.
"""
from __future__ import annotations

import dataclasses as dc
import datetime as dt
from typing import Callable, Literal

from fsl.hashing import stable_hash
from fsl.temporal.time_machine import HistoryView

Scope = Literal["ALL", "HOME_ONLY", "AWAY_ONLY"]
SeasonTransition = Literal["SEASON_RESET", "ROLLING_CONTINUOUS", "WEIGHTED_CARRYOVER"]
Status = Literal["ACTIVE", "EXPERIMENTAL", "LIMITED", "PARKED", "DEPRECATED", "KILLED"]


@dc.dataclass(frozen=True)
class PreMatchContext:
    """Всё, что известно до стартового свистка. Исхода здесь нет намеренно."""
    fixture_id: int
    league: str
    season: str
    kickoff_utc: dt.datetime
    kickoff_precision: str
    sync_batch: int
    home_team: str
    away_team: str


@dc.dataclass(frozen=True)
class FeatureSpec:
    feature_id: str
    version: int
    name: str
    family: str
    description: str
    window: int | None
    scope: Scope
    season_transition: SeasonTransition
    minimum_history: int
    compute: Callable[[PreMatchContext, HistoryView, HistoryView], float | None]
    missing_data_policy: str = "UNAVAILABLE"     # никогда не 0
    status: Status = "EXPERIMENTAL"

    @property
    def key(self) -> str:
        return f"{self.feature_id}.v{self.version}"

    def definition_hash(self) -> str:
        return stable_hash({
            "feature_id": self.feature_id, "version": self.version, "family": self.family,
            "window": self.window, "scope": self.scope,
            "season_transition": self.season_transition,
            "minimum_history": self.minimum_history,
            "missing_data_policy": self.missing_data_policy,
        })


class FeatureRegistry:
    def __init__(self):
        self._specs: dict[str, FeatureSpec] = {}

    def register(self, spec: FeatureSpec) -> FeatureSpec:
        if spec.key in self._specs:
            raise ValueError(f"признак {spec.key} уже зарегистрирован")
        self._specs[spec.key] = spec
        return spec

    def get(self, key: str) -> FeatureSpec:
        return self._specs[key]

    def all(self) -> list[FeatureSpec]:
        return list(self._specs.values())

    def active(self) -> list[FeatureSpec]:
        return [s for s in self._specs.values() if s.status == "ACTIVE"]


REGISTRY = FeatureRegistry()
