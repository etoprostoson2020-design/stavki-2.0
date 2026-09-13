"""Hypothesis Generator.

Документ 04: генератор отвечает «что проверить», Experiment Engine — «что
получилось». Генератор не объявляет стратегии успешными и вообще ничего не
считает: он выпускает кандидатов.

Два жёстких правила, встроенных в код:

1. **Память спрашивается ДО выпуска.** Гипотеза, про которую память уже всё
   знает, до эксперимента не доходит. Это не оптимизация, а условие того,
   чтобы учёт множественного тестирования оставался честным: пересчитывать
   одно и то же — значит раздувать число проверок без нового знания.
2. **Бюджет ограничивает выпуск, а не расчёт.** Исчерпан бюджет — батч
   закрывается, даже если в сетке остались комбинации.
"""
from __future__ import annotations

import dataclasses as dc
from collections import Counter

import numpy as np

from fsl.generator import mutation as mut
from fsl.generator.budget import BudgetExceeded, ResearchBudget
from fsl.generator.grammar import Hypothesis
from fsl.generator.systematic import enumerate_interactions, enumerate_single
from fsl.hashing import stable_hash
from fsl.logging import get_logger
from fsl.memory import dedupe
from fsl.memory import registry as reg
from fsl.memory.fingerprints import region_key
from fsl.memory.regions import is_exhausted
from fsl.validation.policy import Policy

log = get_logger(__name__)


@dc.dataclass
class GenerationResult:
    batch_key: str
    research_question: str
    emitted: list[Hypothesis]
    skipped: list[dict]
    budget: dict
    memory_verdicts: dict
    mode_mix: dict
    seed: int

    def as_dict(self) -> dict:
        return {"batch_key": self.batch_key, "research_question": self.research_question,
                "emitted": len(self.emitted), "skipped": len(self.skipped),
                "budget": self.budget, "memory_verdicts": self.memory_verdicts,
                "mode_mix": self.mode_mix, "seed": self.seed}


class HypothesisGenerator:
    def __init__(self, sess, search_policy: Policy, *, dataset_version: str,
                 feature_versions: dict, policy_hashes: dict, seed: int | None = None):
        self.sess = sess
        self.sp = search_policy
        self.dsv = dataset_version
        self.fvers = feature_versions
        self.pol = policy_hashes
        self.seed = seed if seed is not None else \
            search_policy.get("reproducibility", "seed", default=0)
        self.rng = np.random.default_rng(self.seed)
        self.budget = ResearchBudget.from_policy(search_policy)

    # ------------------------------------------------------------ память
    def _memory_gate(self, hyp: Hypothesis) -> tuple[bool, dict]:
        """Пропускать ли гипотезу к расчёту. Вызывается ДО эксперимента."""
        rk = region_key(list(hyp.conditions), hyp.target)
        if is_exhausted(self.sess, rk, self.dsv) is not None:
            return False, {"hypothesis_key": hyp.hypothesis_key, "verdict": "REGION_EXHAUSTED",
                           "detail": f"область {rk} исчерпана на этом датасете"}
        d = dedupe.check(self.sess, list(hyp.conditions), hyp.target,
                         dataset_version=self.dsv, feature_versions=self.fvers,
                         policy_hashes=self.pol)
        if not d.should_evaluate:
            return False, {"hypothesis_key": hyp.hypothesis_key, "verdict": d.verdict,
                           "detail": d.detail, "known": d.known_hypothesis_id}
        return True, {"hypothesis_key": hyp.hypothesis_key, "verdict": d.verdict}

    # -------------------------------------------------------- систематика
    def systematic(self, values, features: list[str], targets: list[str], *,
                   league: str = "ESP_1", seasons: list[str] | None = None
                   ) -> list[Hypothesis]:
        self.budget.check_inputs(features, targets)
        g = self.sp.get("grammar", default={})
        tp = self.sp.get("team_policy", default={})
        q = self.sp.get("thresholds", "coarse_grid", default=[0.1, 0.9])
        maxc = g.get("max_complexity", 4)
        seasons = list(seasons or [])

        pool = enumerate_single(values, features, targets, q, league=league,
                                seasons=seasons, team_policy=tp, max_complexity=maxc)
        if g.get("max_conditions", 2) >= 2:
            pool += enumerate_interactions(values, features, targets, q, league=league,
                                           seasons=seasons, team_policy=tp,
                                           max_complexity=maxc)
        return pool

    # ------------------------------------------------------------ мутации
    def mutations(self, parents: list[Hypothesis], *, window_map: dict[str, str],
                  extra_conditions: list) -> list[Hypothesis]:
        g = self.sp.get("grammar", default={})
        maxc = g.get("max_conditions_by_mutation", 3)
        deltas = self.sp.get("thresholds", "fine_neighborhood", default=[-0.1, 0.1])
        out: list[Hypothesis] = []
        for p in parents:
            if p.generation >= self.budget.max_generations:
                continue
            # Виды мутаций держим раздельно: если тратить бюджет по порядку
            # общего списка, поздние виды (добавить и снять условие) никогда
            # не доходят до выпуска, и соседство порога съедает всю квоту.
            by_kind = {
                "threshold": mut.mutate_threshold(p, deltas, maxc),
                "window": mut.mutate_window(p, window_map, maxc),
                "operator": mut.mutate_operator(p, maxc),
                "add_condition": mut.mutate_add_condition(p, extra_conditions, maxc),
                "drop_condition": mut.mutate_drop_condition(p, maxc),
            }
            for kind in by_kind:                       # порядок внутри вида — свой
                by_kind[kind] = sorted(by_kind[kind], key=lambda h: h.hypothesis_key)

            # Круговой обход: каждый вид получает шанс, пока не кончится квота.
            kinds = [k for k, v in by_kind.items() if v]
            cursor = {k: 0 for k in kinds}
            while kinds and self.budget.can_mutate(p.hypothesis_key):
                progressed = False
                for kind in list(kinds):
                    if not self.budget.can_mutate(p.hypothesis_key):
                        break
                    i = cursor[kind]
                    if i >= len(by_kind[kind]):
                        kinds.remove(kind)
                        continue
                    cursor[kind] = i + 1
                    self.budget.spend_mutation(p.hypothesis_key)
                    out.append(by_kind[kind][i])
                    progressed = True
                if not progressed:
                    break
        return out

    def promising_parents(self, pool: list[Hypothesis], *, min_abs_z: float,
                          limit: int = 5) -> list[Hypothesis]:
        """Родители для мутаций берутся ИЗ ПАМЯТИ, а не из свежих подсчётов.

        Тонкое соседство разрешено только вокруг уже показавшего себя
        кандидата — иначе это скрытая оптимизация порога.
        """
        by_key = {h.hypothesis_key: h for h in pool}
        scored = []
        for h in pool:
            rec = reg.find_exact(self.sess, list(h.conditions), h.target, self.dsv,
                                 self.fvers, self.pol)
            if rec is not None and rec.z is not None and abs(rec.z) >= min_abs_z:
                scored.append((abs(rec.z), h.hypothesis_key))
        scored.sort(reverse=True)
        return [by_key[k] for _, k in scored[:limit]]

    # -------------------------------------------------------------- выпуск
    def emit(self, pool: list[Hypothesis], research_question: str) -> GenerationResult:
        """Прогоняет пул через память и бюджет. Ничего не считает."""
        pool = sorted(pool, key=lambda h: h.hypothesis_key)      # детерминизм
        emitted: list[Hypothesis] = []
        skipped: list[dict] = []
        verdicts: Counter = Counter()

        share = self.sp.get("exploration", "exploitation_share", default=0.7)
        floor = self.sp.get("exploration", "exploration_floor", default=0.3)
        seen_families: Counter = Counter()
        cap_per_family = max(int(self.budget.max_hypotheses * share), 1)

        for hyp in pool:
            if not self.budget.can_spend():
                skipped.append({"hypothesis_key": hyp.hypothesis_key,
                                "verdict": "BUDGET_EXHAUSTED", "detail": "бюджет батча"})
                verdicts["BUDGET_EXHAUSTED"] += 1
                continue
            ok, info = self._memory_gate(hyp)
            verdicts[info["verdict"]] += 1
            if not ok:
                skipped.append(info)
                continue
            if seen_families[hyp.family] >= cap_per_family:
                skipped.append({"hypothesis_key": hyp.hypothesis_key,
                                "verdict": "FAMILY_CAP",
                                "detail": f"доля семейства {hyp.family} исчерпана, "
                                          f"место резервируется под exploration "
                                          f"(floor {floor})"})
                verdicts["FAMILY_CAP"] += 1
                continue
            self.budget.spend()
            seen_families[hyp.family] += 1
            emitted.append(hyp)

        key = "GEN-" + stable_hash({"q": research_question, "seed": self.seed,
                                    "keys": [h.hypothesis_key for h in emitted]})[:10]
        res = GenerationResult(
            batch_key=key, research_question=research_question, emitted=emitted,
            skipped=skipped, budget=self.budget.report(),
            memory_verdicts=dict(verdicts),
            mode_mix=dict(Counter(h.mode for h in emitted)), seed=self.seed)
        log.info("generator.emit", batch=key, emitted=len(emitted),
                 skipped=len(skipped), seed=self.seed)
        return res
