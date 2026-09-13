"""Систематический перебор: одиночные условия и парные взаимодействия."""
from __future__ import annotations

import itertools

from fsl.experiments.engine import Condition
from fsl.generator.grammar import (Hypothesis, complexity_of, feature_class,
                                   make_key, type_of)
from fsl.generator.thresholds import coarse_grid


def _allowed(feature_key: str, team_policy: dict) -> bool:
    cls = feature_class(feature_key)
    return {"TEAM_RELATIVE": team_policy.get("allow_team_relative", True),
            "TEAM_SPECIFIC": team_policy.get("allow_team_specific", False),
            "LEAGUE_STATE": team_policy.get("allow_league_state", True)}[cls]


def enumerate_single(values, features: list[str], targets: list[str],
                     quantiles: list[float], *, league: str, seasons: list[str],
                     team_policy: dict, max_complexity: int) -> list[Hypothesis]:
    out = []
    for fk in features:
        if not _allowed(fk, team_policy):
            continue
        for op, thr in coarse_grid(values, fk, quantiles):
            conds = (Condition(fk, op, thr),)
            cx = complexity_of(conds)
            if cx > max_complexity:
                continue
            for t in targets:
                out.append(Hypothesis(
                    hypothesis_key=make_key(conds, t), conditions=conds, target=t,
                    htype=type_of(conds), origin="RULE_GENERATOR", mode="SYSTEMATIC",
                    family=fk.split(".")[0], league=league, seasons=tuple(seasons),
                    complexity=cx))
    return out


def enumerate_interactions(values, features: list[str], targets: list[str],
                           quantiles: list[float], *, league: str, seasons: list[str],
                           team_policy: dict, max_complexity: int,
                           max_pairs_per_feature: int = 2) -> list[Hypothesis]:
    """Пары условий на РАЗНЫХ признаках.

    Пара на одном признаке — это интервал, а не взаимодействие, и она резко
    сужает выборку без нового смысла, поэтому исключена.
    """
    out = []
    usable = [f for f in features if _allowed(f, team_policy)]
    grids = {f: coarse_grid(values, f, quantiles) for f in usable}
    for a, b in itertools.combinations(usable, 2):
        if a.split(".")[0] == b.split(".")[0]:
            continue                      # то же семейство — не взаимодействие
        ga = grids[a][:max_pairs_per_feature]
        gb = grids[b][:max_pairs_per_feature]
        for (opa, ta), (opb, tb) in itertools.product(ga, gb):
            conds = (Condition(a, opa, ta), Condition(b, opb, tb))
            cx = complexity_of(conds)
            if cx > max_complexity:
                continue
            for t in targets:
                out.append(Hypothesis(
                    hypothesis_key=make_key(conds, t), conditions=conds, target=t,
                    htype=type_of(conds), origin="RULE_GENERATOR", mode="SYSTEMATIC",
                    family=f"{a.split('.')[0]}+{b.split('.')[0]}",
                    league=league, seasons=tuple(seasons), complexity=cx))
    return out
