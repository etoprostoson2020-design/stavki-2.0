"""Фаза 8. Hypothesis Generator на реальных данных.

Показывает:
  1. генератор спрашивает память ДО выпуска и не отдаёт на расчёт известное;
  2. бюджет ограничивает выпуск, а не скорость;
  3. мутации идут только от родителей, уже показавших себя, и несут родословную;
  4. правила про конкретный клуб не выпускаются по умолчанию;
  5. один и тот же seed при тех же данных даёт тот же батч.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from fsl import logging as fsl_logging
from fsl.canonical.builder import dataset_version_for
from fsl.db import session
from fsl.experiments.engine import Condition
from fsl.features import catalogue  # noqa: F401
from fsl.features.compute import compute_features
from fsl.features.registry import REGISTRY
from fsl.generator.generator import HypothesisGenerator
from fsl.generator.grammar import feature_class
from fsl.generator.mutation import lineage
from fsl.models import GenerationRun
from fsl.validation.policy import (load_policy, qualification_policy,
                                   statistical_policy)
from scripts.run_slice import BLOCKS, FEATURE_KEYS, LEAGUE, load_fixtures

TARGETS = ["RES_HOME", "RES_AWAY", "OVER_25", "BTTS_YES"]
WINDOW_MAP = {"FORM_PPG_DIFF.v1": "FORM_PPG_DIFF.v2",
              "FORM_PPG_DIFF.v2": "FORM_PPG_DIFF.v1"}


def _make(sess, sp, dsv, fvers, pol, seed=None):
    return HypothesisGenerator(sess, sp, dataset_version=dsv, feature_versions=fvers,
                               policy_hashes=pol, seed=seed)


def main() -> dict:
    fsl_logging.configure("WARNING")
    sp = load_policy("search_policy.yaml", "SEARCH_POLICY")
    qual, stat = qualification_policy(), statistical_policy()
    pol = {"qualification": qual.hash, "statistical": stat.hash}
    out: dict = {}

    with session() as s:
        seasons = BLOCKS["DISCOVERY"]
        dsv = dataset_version_for(s, LEAGUE, seasons)
        fixtures = load_fixtures(s, LEAGUE, seasons)
        specs = [REGISTRY.get(k) for k in FEATURE_KEYS]
        values = compute_features(fixtures, specs)
        fvers = {sp_.key: sp_.definition_hash() for sp_ in specs}

        print(f"\nSEARCH POLICY  {sp.version} hash {sp.hash} | seed "
              f"{sp.get('reproducibility', 'seed')}")
        print(f"               max условий {sp.get('grammar','max_conditions')} | "
              f"max сложность {sp.get('grammar','max_complexity')} | "
              f"бюджет {sp.get('budget','max_hypotheses_per_batch')}")

        # --- 1. Классификация признаков и team-политика ----------------------
        print("\nTEAM POLICY")
        for fk in FEATURE_KEYS:
            print(f"               {fk:22} класс {feature_class(fk)}")
        print(f"               TEAM_RELATIVE разрешён: "
              f"{sp.get('team_policy','allow_team_relative')} | "
              f"TEAM_SPECIFIC (правила про конкретный клуб): "
              f"{sp.get('team_policy','allow_team_specific')}")

        # --- 2. Систематический перебор --------------------------------------
        gen = _make(s, sp, dsv, fvers, pol)
        pool = gen.systematic(values, FEATURE_KEYS, TARGETS, league=LEAGUE,
                              seasons=seasons)
        by_type = Counter(h.htype for h in pool)
        print(f"\nПУЛ            гипотез в сетке {len(pool)} | по типам {dict(by_type)}")
        out["pool"] = len(pool)

        # --- 3. Память ДО расчёта, затем бюджет ------------------------------
        res = gen.emit(pool, "форма, голы и отдых против исходов матча")
        print(f"\nВЫПУСК         батч {res.batch_key}")
        print(f"               выпущено {len(res.emitted)} | отсеяно {len(res.skipped)}")
        print(f"               вердикты памяти: {res.memory_verdicts}")
        print(f"               бюджет: {res.budget}")
        out["first"] = res.as_dict()
        for sk in res.skipped[:3]:
            print(f"               пример отсева: {sk['verdict']} — "
                  f"{sk.get('detail','')[:70]}")

        # --- 4. Мутации от многообещающих родителей --------------------------
        parents = gen.promising_parents(pool, min_abs_z=5.0, limit=3)
        print(f"\nМУТАЦИИ        родителей из памяти (|z| >= 5.0): {len(parents)}")
        for p in parents:
            print(f"               {p.hypothesis_key}")
        extra = [Condition("REST_DAYS_DIFF.v1", ">=", 1.0)]
        children = gen.mutations(parents, window_map=WINDOW_MAP, extra_conditions=extra)
        print(f"               потомков {len(children)} | "
              f"поколение {sorted({c.generation for c in children}) or '—'}")
        kinds = Counter(c.mutation_reason.split(":")[0] for c in children)
        print(f"               виды мутаций: {dict(kinds)}")
        out["mutations"] = len(children)

        if children:
            index = {h.hypothesis_key: h for h in pool + children}
            ch = children[0]
            print(f"               родословная: {' -> '.join(lineage(ch, index))}")
            print(f"               причина: {ch.mutation_reason}")

        res_mut = gen.emit(children, "соседство вокруг подтверждённых родителей")
        print(f"               выпущено мутаций {len(res_mut.emitted)} | "
              f"отсеяно {len(res_mut.skipped)} | вердикты {res_mut.memory_verdicts}")
        out["mutations_emitted"] = len(res_mut.emitted)

        # --- 5. Детерминизм ---------------------------------------------------
        gen2 = _make(s, sp, dsv, fvers, pol)
        pool2 = gen2.systematic(values, FEATURE_KEYS, TARGETS, league=LEAGUE,
                                seasons=seasons)
        res2 = gen2.emit(pool2, "форма, голы и отдых против исходов матча")
        same = res2.batch_key == res.batch_key
        print(f"\nДЕТЕРМИНИЗМ    повтор с тем же seed: батч {res2.batch_key} | "
              f"{'совпал' if same else 'РАСХОЖДЕНИЕ'}")
        out["deterministic"] = same

        # --- 6. Бюджет как ограничитель ---------------------------------------
        tight = load_policy("search_policy.yaml", "SEARCH_POLICY")
        tight = type(tight)(tight.name, tight.version,
                            {**tight.payload,
                             "budget": {**tight.payload["budget"],
                                        "max_hypotheses_per_batch": 5}})
        gen3 = _make(s, tight, dsv, fvers, pol)
        res3 = gen3.emit(pool, "тот же пул при бюджете 5")
        print(f"\nБЮДЖЕТ         при лимите 5: выпущено {len(res3.emitted)}, "
              f"отсеяно по бюджету "
              f"{res3.memory_verdicts.get('BUDGET_EXHAUSTED', 0)}")
        out["budget_capped"] = len(res3.emitted)

        # --- 7. Запись прогона -------------------------------------------------
        if s.scalar(select(GenerationRun).where(
                GenerationRun.batch_key == res.batch_key)) is None:
            s.add(GenerationRun(
                batch_key=res.batch_key, research_question=res.research_question,
                league=LEAGUE, dataset_version=dsv, search_policy_hash=sp.hash,
                seed=res.seed, mode_mix=res.mode_mix, n_pool=len(pool),
                n_emitted=len(res.emitted), n_skipped=len(res.skipped),
                memory_verdicts=res.memory_verdicts, budget=res.budget))
            print(f"\nЗАПИСАНО       прогон {res.batch_key}")
        else:
            print(f"\nЗАПИСАНО       прогон {res.batch_key} уже есть — повтора нет")
    return out


if __name__ == "__main__":
    main()
