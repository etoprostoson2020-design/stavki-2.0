"""Мутации с родословной.

Документ 04 разрешает: окно, порог, родственный признак, добавление или снятие
одного условия, смена оператора. Каждая мутация создаёт lineage; число
поколений ограничено бюджетом.
"""
from __future__ import annotations

from fsl.experiments.engine import Condition
from fsl.generator.grammar import Hypothesis, complexity_of, make_key, type_of
from fsl.generator.thresholds import fine_neighborhood

FLIP = {">=": "<=", "<=": ">="}


def _child(parent: Hypothesis, conds, reason: str, max_complexity: int
           ) -> Hypothesis | None:
    cx = complexity_of(conds)
    if cx > max_complexity:
        return None
    return Hypothesis(
        hypothesis_key=make_key(conds, parent.target), conditions=tuple(conds),
        target=parent.target, htype=type_of(conds), origin="MUTATION",
        mode="MUTATION", family=parent.family, league=parent.league,
        seasons=parent.seasons, complexity=cx, generation=parent.generation + 1,
        parent_key=parent.hypothesis_key, mutation_reason=reason)


def mutate_threshold(parent: Hypothesis, deltas: list[float],
                     max_complexity: int) -> list[Hypothesis]:
    """Шаг порога. Соседство вокруг многообещающего родителя, не поиск заново."""
    out = []
    for i, c in enumerate(parent.conditions):
        for op, thr in fine_neighborhood(c.op, c.threshold, deltas):
            conds = list(parent.conditions)
            conds[i] = Condition(c.feature_key, op, thr)
            ch = _child(parent, conds, f"порог {c.feature_key}: {c.threshold} -> {thr}",
                        max_complexity)
            if ch:
                out.append(ch)
    return out


def mutate_window(parent: Hypothesis, window_map: dict[str, str],
                  max_complexity: int) -> list[Hypothesis]:
    """Тот же признак на соседнем окне: v1 <-> v2."""
    out = []
    for i, c in enumerate(parent.conditions):
        alt = window_map.get(c.feature_key)
        if not alt:
            continue
        conds = list(parent.conditions)
        conds[i] = Condition(alt, c.op, c.threshold)
        ch = _child(parent, conds, f"окно: {c.feature_key} -> {alt}", max_complexity)
        if ch:
            out.append(ch)
    return out


def mutate_operator(parent: Hypothesis, max_complexity: int) -> list[Hypothesis]:
    """Переворот направления: проверка, что эффект не артефакт знака."""
    out = []
    for i, c in enumerate(parent.conditions):
        conds = list(parent.conditions)
        conds[i] = Condition(c.feature_key, FLIP[c.op], c.threshold)
        ch = _child(parent, conds, f"оператор {c.feature_key}: {c.op} -> {FLIP[c.op]}",
                    max_complexity)
        if ch:
            out.append(ch)
    return out


def mutate_add_condition(parent: Hypothesis, extra: list[Condition],
                         max_complexity: int) -> list[Hypothesis]:
    out = []
    have = {c.feature_key.split(".")[0] for c in parent.conditions}
    for c in extra:
        if c.feature_key.split(".")[0] in have:
            continue
        ch = _child(parent, list(parent.conditions) + [c],
                    f"добавлено условие {c.feature_key}", max_complexity)
        if ch:
            out.append(ch)
    return out


def mutate_drop_condition(parent: Hypothesis, max_complexity: int) -> list[Hypothesis]:
    """Снятие условия: не держится ли эффект на одном плече."""
    if len(parent.conditions) < 2:
        return []
    out = []
    for i, c in enumerate(parent.conditions):
        conds = [x for j, x in enumerate(parent.conditions) if j != i]
        ch = _child(parent, conds, f"снято условие {c.feature_key}", max_complexity)
        if ch:
            out.append(ch)
    return out


def lineage(hyp: Hypothesis, index: dict[str, Hypothesis]) -> list[str]:
    """Цепочка предков до корня."""
    chain, cur = [hyp.hypothesis_key], hyp
    seen = {hyp.hypothesis_key}
    while cur.parent_key and cur.parent_key in index:
        if cur.parent_key in seen:
            break
        chain.append(cur.parent_key)
        seen.add(cur.parent_key)
        cur = index[cur.parent_key]
    return list(reversed(chain))
