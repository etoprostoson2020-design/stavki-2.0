"""Фаза 8, приёмка по документу 10.

Single/difference/sum/two-feature/simple-sequence, Search Budget, max complexity,
TEAM-BLIND по умолчанию, воспроизводимость по seed и обязательная проверка
памяти ДО расчёта.
"""
from __future__ import annotations

from collections import Counter

import pytest

from fsl.experiments.engine import Condition
from fsl.generator.budget import BudgetExceeded, ResearchBudget
from fsl.generator.generator import HypothesisGenerator
from fsl.generator.grammar import Hypothesis, complexity_of, feature_class, type_of
from fsl.generator.mutation import lineage
from fsl.memory import registry as reg
from fsl.memory.regions import mark_exhausted_regions
from fsl.validation.policy import Policy, load_policy

SP = load_policy("search_policy.yaml", "SEARCH_POLICY")
POL = {"qualification": "qh", "statistical": "sh"}
FV = {"F_A.v1": "h1", "F_B.v1": "h2"}
TARGETS = ["RES_HOME", "OVER_25"]
FEATURES = ["F_A.v1", "F_B.v1"]


def values(n=400):
    """Два признака с известным распределением: пороги предсказуемы."""
    return {i: {"F_A.v1": float(i % 20) - 10.0, "F_B.v1": float((i * 7) % 15) - 7.0}
            for i in range(1, n + 1)}


def _gen(sess, policy=SP, seed=None):
    return HypothesisGenerator(sess, policy, dataset_version="dsv1",
                               feature_versions=FV, policy_hashes=POL, seed=seed)


# ------------------------------------------------------------- грамматика
def test_hypothesis_types_and_complexity():
    a = [Condition("F_A.v1", ">=", 1.0)]
    b = [Condition("F_A.v1", ">=", 1.0), Condition("F_B.v1", "<=", 2.0)]
    assert type_of(a) == "SINGLE" and type_of(b) == "INTERACTION"
    assert type_of([Condition("FORM_PPG_DIFF.v1", ">=", 0.0)]) == "DIFFERENCE"
    assert complexity_of(a) == 1
    assert complexity_of(b) == 3          # два условия + лишнее семейство


def test_max_conditions_respected(sess):
    pool = _gen(sess).systematic(values(), FEATURES, TARGETS)
    assert all(len(h.conditions) <= SP.get("grammar", "max_conditions") for h in pool)


def test_complexity_cap_respected(sess):
    cap = SP.get("grammar", "max_complexity")
    pool = _gen(sess).systematic(values(), FEATURES, TARGETS)
    assert all(h.complexity <= cap for h in pool)


def test_interaction_pairs_use_different_families(sess):
    pool = _gen(sess).systematic(values(), FEATURES, TARGETS)
    for h in pool:
        if len(h.conditions) == 2:
            fams = {c.feature_key.split(".")[0] for c in h.conditions}
            assert len(fams) == 2, "пара на одном признаке — это интервал, не взаимодействие"


# ------------------------------------------------------ team-политика
def test_team_specific_rules_are_not_emitted_by_default(sess):
    """Разбор архитектуры 6.2: скользящие окна разрешены, имена клубов — нет."""
    assert feature_class("FORM_PPG_DIFF.v1") == "TEAM_RELATIVE"
    assert SP.get("team_policy", "allow_team_relative") is True
    assert SP.get("team_policy", "allow_team_specific") is False

    strict = Policy(SP.name, SP.version,
                    {**SP.payload, "team_policy": {**SP.payload["team_policy"],
                                                   "allow_team_relative": False}})
    pool = _gen(sess, strict).systematic(values(), FEATURES, TARGETS)
    assert pool == [], "при запрете TEAM_RELATIVE выпускать нечего"


# --------------------------------------------------------------- бюджет
def test_budget_caps_emission(sess):
    """Бюджет ограничивает выпуск. Доля семейства может отсечь раньше него —
    место резервируется под exploration, и это отдельная причина отсева."""
    tight = Policy(SP.name, SP.version,
                   {**SP.payload, "budget": {**SP.payload["budget"],
                                             "max_hypotheses_per_batch": 7}})
    g = _gen(sess, tight)
    pool = g.systematic(values(), FEATURES, TARGETS)
    res = g.emit(pool, "лимит семь")
    assert len(res.emitted) == 7
    # каждая невыпущенная гипотеза отсеяна с названной причиной, без потерь
    assert len(res.emitted) + len(res.skipped) == len(pool)
    assert res.memory_verdicts.get("BUDGET_EXHAUSTED", 0) > 0
    assert res.budget["remaining"] == 0


def test_budget_rejects_too_many_features(sess):
    b = ResearchBudget.from_policy(SP)
    with pytest.raises(BudgetExceeded, match="признаков"):
        b.check_inputs([f"F{i}.v1" for i in range(50)], TARGETS)


def test_mutation_quota_is_shared_across_kinds(sess):
    """Квота не должна съедаться одним видом мутации."""
    parent = Hypothesis(hypothesis_key="F_A.v1>=1.0->RES_HOME",
                        conditions=(Condition("F_A.v1", ">=", 1.0),),
                        target="RES_HOME", htype="SINGLE", origin="RULE_GENERATOR",
                        mode="SYSTEMATIC", family="F_A", league="ESP_1",
                        seasons=("S1",), complexity=1)
    g = _gen(sess)
    kids = g.mutations([parent], window_map={"F_A.v1": "F_A.v2"},
                       extra_conditions=[Condition("F_B.v1", ">=", 0.5)])
    kinds = {k.mutation_reason.split(" ")[0] for k in kids}
    assert len(kids) == SP.get("budget", "max_mutations_per_parent")
    assert len(kinds) >= 3, f"квоту забрал один вид мутации: {kinds}"


def test_mutation_lineage_and_generation(sess):
    parent = Hypothesis(hypothesis_key="F_A.v1>=1.0->RES_HOME",
                        conditions=(Condition("F_A.v1", ">=", 1.0),),
                        target="RES_HOME", htype="SINGLE", origin="RULE_GENERATOR",
                        mode="SYSTEMATIC", family="F_A", league="ESP_1",
                        seasons=("S1",), complexity=1)
    kids = _gen(sess).mutations([parent], window_map={}, extra_conditions=[])
    assert kids and all(k.generation == 1 for k in kids)
    assert all(k.parent_key == parent.hypothesis_key for k in kids)
    assert all(k.origin == "MUTATION" and k.mutation_reason for k in kids)
    index = {h.hypothesis_key: h for h in [parent] + kids}
    assert lineage(kids[0], index)[0] == parent.hypothesis_key


def test_generations_are_capped(sess):
    deep = Hypothesis(hypothesis_key="k", conditions=(Condition("F_A.v1", ">=", 1.0),),
                      target="RES_HOME", htype="SINGLE", origin="MUTATION",
                      mode="MUTATION", family="F_A", league="ESP_1", seasons=("S1",),
                      complexity=1, generation=SP.get("budget", "max_generations"))
    assert _gen(sess).mutations([deep], window_map={}, extra_conditions=[]) == []


# ---------------------------------------------------- память перед расчётом
def test_known_hypothesis_is_not_emitted(sess):
    g = _gen(sess)
    pool = g.systematic(values(), FEATURES, TARGETS)
    first = pool[0]
    reg.record_hypothesis(sess, league="ESP_1", seasons=["S1"],
                          conditions=list(first.conditions), target=first.target,
                          feature_versions=FV, dataset_version="dsv1",
                          policy_hashes=POL, result={"n_signals": 10, "z": 2.0})
    res = _gen(sess).emit(pool, "вопрос")
    keys = {h.hypothesis_key for h in res.emitted}
    assert first.hypothesis_key not in keys
    assert res.memory_verdicts.get("EXACT_DUPLICATE", 0) >= 1


def test_exhausted_region_is_not_emitted(sess):
    for thr in range(8):
        reg.record_hypothesis(sess, league="ESP_1", seasons=["S1"],
                              conditions=[Condition("F_A.v1", ">=", float(thr))],
                              target="RES_HOME", feature_versions=FV,
                              dataset_version="dsv1", policy_hashes=POL,
                              result={"n_signals": 50, "z": 1.0},
                              passed_threshold=False)
    mark_exhausted_regions(sess, "ESP_1", "dsv1", batch_threshold=3.0, min_tested=6)
    g = _gen(sess)
    res = g.emit(g.systematic(values(), FEATURES, TARGETS), "вопрос")
    assert res.memory_verdicts.get("REGION_EXHAUSTED", 0) > 0
    assert all(not (h.target == "RES_HOME" and h.conditions[0].op == ">="
                    and h.conditions[0].feature_key == "F_A.v1")
               for h in res.emitted if len(h.conditions) == 1)


# --------------------------------------------------------- воспроизводимость
def test_same_seed_gives_same_batch(sess):
    a = _gen(sess, seed=42)
    b = _gen(sess, seed=42)
    ra = a.emit(a.systematic(values(), FEATURES, TARGETS), "вопрос")
    rb = b.emit(b.systematic(values(), FEATURES, TARGETS), "вопрос")
    assert ra.batch_key == rb.batch_key
    assert [h.hypothesis_key for h in ra.emitted] == [h.hypothesis_key for h in rb.emitted]


def test_generator_does_not_evaluate(sess):
    """Генератор отвечает «что проверить», а не «что получилось»."""
    pool = _gen(sess).systematic(values(), FEATURES, TARGETS)
    forbidden = ("z", "hit_rate", "baseline", "uplift", "outcome", "verdict")
    for name in forbidden:
        assert not hasattr(pool[0], name), f"в гипотезе оказалось поле результата: {name}"
    assert Counter(h.origin for h in pool) == {"RULE_GENERATOR": len(pool)}
