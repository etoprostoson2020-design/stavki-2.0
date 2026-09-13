"""Фаза 7. Research Memory на реальных данных.

Показывает:
  1. батч начинается с обращения к памяти, а не с расчёта;
  2. повторный тот же батч распознаётся как дубликаты и не считается заново;
  3. области, где искали и не нашли, помечаются исчерпанными;
  4. PARK и KILL хранят причину и условие возврата;
  5. память отвечает «мы это уже проверяли и чем кончилось» без чтения файлов.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import select

from fsl import logging as fsl_logging
from fsl.canonical.builder import dataset_version_for
from fsl.db import session
from fsl.experiments.engine import Condition
from fsl.features import catalogue  # noqa: F401
from fsl.features.compute import compute_features
from fsl.features.registry import REGISTRY
from fsl.memory import api as memory
from fsl.memory import families, lifecycle, regions
from fsl.memory import registry as reg
from fsl.models import Strategy
from fsl.validation.policy import qualification_policy, statistical_policy
from fsl.validation.search_batch import build_matrices, z_scores
from scripts.run_slice import BLOCKS, FEATURE_KEYS, LEAGUE, load_fixtures
from scripts.run_validation import TARGET_SET, build_batch

#: Сетка плотнее, чем в фазе 6: чтобы область можно было признать
#: исчерпанной, в ней должно быть проверено достаточно порогов.
QUANTILES = [0.05, 0.10, 0.20, 0.30, 0.35, 0.40,
             0.60, 0.65, 0.70, 0.80, 0.90, 0.95]

POLICY_VERSION = "QUALIFICATION_POLICY_v0.1"


def main() -> dict:
    fsl_logging.configure("WARNING")
    qual, stat = qualification_policy(), statistical_policy()
    pol = {"qualification": qual.hash, "statistical": stat.hash}
    out: dict = {}

    with session() as s:
        seasons = BLOCKS["DISCOVERY"]
        dsv = dataset_version_for(s, LEAGUE, seasons)
        fixtures = load_fixtures(s, LEAGUE, seasons)
        specs = [REGISTRY.get(k) for k in FEATURE_KEYS]
        values = compute_features(fixtures, specs)
        fvers = {sp.key: sp.definition_hash() for sp in specs}
        cands = build_batch(values, FEATURE_KEYS, TARGET_SET, QUANTILES)

        # --- 1. Память ДО расчёта -------------------------------------------
        ctx = memory.get_memory_context(s, cands, dataset_version=dsv,
                                        feature_versions=fvers, policy_hashes=pol)
        print(f"\nMEMORY CONTEXT (до расчёта)")
        print(f"           кандидатов на входе {ctx['candidates_in']} | "
              f"считать {ctx['to_evaluate']} | пропустить {ctx['skipped']}")
        print(f"           вердикты: {ctx['verdicts']}")
        print(f"           в реестре гипотез {ctx['registry']['hypotheses']}, "
              f"встреч дубликатов {ctx['registry']['duplicate_encounters']}")
        out["context_before"] = {k: ctx[k] for k in
                                 ("candidates_in", "to_evaluate", "skipped", "verdicts")}

        # --- 2. Расчёт и запись в реестр ------------------------------------
        bm = build_matrices(fixtures, values, cands)
        z = z_scores(bm)
        threshold = 3.09          # порог батча из фазы 6
        fid_by_pos = bm.fixture_ids
        new_count = 0
        for i, cand in enumerate(cands):
            sig_ids = [fid_by_pos[j] for j in np.where(bm.signal[i] > 0)[0]]
            ns = int(bm.signal[i].sum())
            ne = int(bm.eligible[i].sum())
            if ne == 0:
                continue
            yc = np.nan_to_num(bm.targets[bm.candidate_target[i]], nan=0.0)
            base = float((bm.eligible[i] * yc).sum() / ne)
            hit = float((bm.signal[i] * yc).sum() / ns) if ns else None
            passed = bool(abs(z[i]) >= threshold) if not np.isnan(z[i]) else False
            _, is_new = reg.record_hypothesis(
                s, league=LEAGUE, seasons=seasons, conditions=list(cand.conditions),
                target=cand.target, feature_versions=fvers, dataset_version=dsv,
                policy_hashes=pol,
                result={"n_signals": ns, "baseline": base, "hit_rate": hit,
                        "absolute_uplift": (hit - base) if hit is not None else None,
                        "z": None if np.isnan(z[i]) else float(z[i])},
                signal_fixture_ids=sig_ids, batch_id="BATCH-4c48b57ca8",
                passed_threshold=passed)
            new_count += is_new
            reg.update_meta(s, list(cand.conditions), cand.target,
                            z=None if np.isnan(z[i]) else float(z[i]), passed=passed)
        print(f"\nЗАПИСЬ     новых гипотез в реестре {new_count} из {len(cands)}")

        # --- 3. Исчерпанные области -----------------------------------------
        from fsl.validation.policy import research_policy
        min_tested = research_policy().get('memory', 'min_hypotheses_to_exhaust',
                                           default=6)
        marked = regions.mark_exhausted_regions(s, LEAGUE, dsv, threshold,
                                                min_tested=min_tested)
        print(f"\nREGIONS    помечено исчерпанными {len(marked)}")
        for m in marked[:6]:
            print(f"           {m['region_key']:44} проверено {m['tested']:3d}, "
                  f"лучший |z| {m['best_abs_z']}")
        out["exhausted"] = marked

        # --- 4. Сигналы стратегии, семейства ---------------------------------
        st = s.scalar(select(Strategy).where(Strategy.strategy_id == "STR-000001"))
        if st is not None:
            conds = [Condition(c["feature"], c["op"], c["threshold"]) for c in st.conditions]
            bm1 = build_matrices(fixtures, values, [type(cands[0])(
                candidate_id="STR-000001", conditions=tuple(conds), target=st.target)])
            sig_ids = [fid_by_pos[j] for j in np.where(bm1.signal[0] > 0)[0]]
            families.store_signals(s, st.strategy_id, st.version, dsv, sig_ids)

            # соседняя версия того же механизма — окно 5 вместо 10
            # тот же признак и то же окно, порог сдвинут на шаг:
            # это одна стратегия, а не второе открытие
            near = [Condition("FORM_PPG_DIFF.v2", "<=", -0.55)]
            bm2 = build_matrices(fixtures, values, [type(cands[0])(
                candidate_id="STR-000002", conditions=tuple(near), target=st.target)])
            near_ids = [fid_by_pos[j] for j in np.where(bm2.signal[0] > 0)[0]]
            families.store_signals(s, "STR-000002", 1, dsv, near_ids)

            fams = families.rebuild_families(s)
            sim = families.similarity_matrix(s)
            print(f"\nFAMILIES   семейств {len(fams)}")
            for f in fams:
                print(f"           {f['family_id']} : {f['members']} "
                      f"| max Jaccard {f['max_pairwise_jaccard']}")
            print(f"           матрица сходства: {sim['members']} -> {sim['jaccard']}")
            out["families"] = fams

        # --- 5. PARK и KILL ---------------------------------------------------
        if st is not None and not s.scalars(select(lifecycle.ParkRecord).where(
                lifecycle.ParkRecord.strategy_id == st.strategy_id)).first():
            lifecycle.park(
                s, st.strategy_id, st.version,
                reason="все четыре условия критерия выполнены, но блок валидации был "
                       "просмотрен до заморозки: независимого OOS у стратегии нет",
                revival_condition="открыт блок test (24-25, 25-26) ИЛИ подключена "
                                  "вторая лига для чистого переноса",
                min_new_fixtures=760, review_days=120, priority=1)
            lifecycle.kill(
                s, "STR-000002", 1, code="DUPLICATE_OF_EXISTING",
                reason="то же множество сигналов, что у STR-000001: это одна "
                       "стратегия на соседнем окне, а не второе открытие",
                evidence={"jaccard_with": "STR-000001.v1"},
                policy_version=POLICY_VERSION)
        print("\nLIFECYCLE  STR-000001 -> PARK, STR-000002 -> KILL")
        for sid in ("STR-000001", "STR-000002"):
            h = lifecycle.failure_history(s, sid)
            for p in h["parks"]:
                print(f"           {sid} PARK: {p['reason'][:70]}...")
                print(f"                     условие возврата: {p['revival_condition']}")
            for k in h["kills"]:
                print(f"           {sid} KILL [{k['code']}]: {k['reason'][:70]}...")

        rev = lifecycle.revival_candidates(s)
        print(f"\nREVIVAL    кандидатов на пересмотр {len(rev)}")
        for r in rev:
            print(f"           {r['strategy_id']} — {r['triggered_by']}, "
                  f"новых матчей {r['new_fixtures']} из {r['min_new_fixtures']}")
        if not rev:
            from fsl.models import Fixture, ParkRecord
            from sqlalchemy import func as _f
            total = s.scalar(select(_f.count()).select_from(Fixture)) or 0
            for p in s.scalars(select(ParkRecord).where(
                    ParkRecord.revived_at.is_(None))).all():
                print(f"           {p.strategy_id}: ждёт "
                      f"{p.min_new_fixtures - (total - p.fixtures_at_park)} новых матчей "
                      f"или пересмотра после {p.review_after.date()}")
        out["revival"] = rev

        # --- 6. Meta Memory ---------------------------------------------------
        meta = reg.meta_summary(s)
        print(f"\nMETA       производительность признаков (топ-6 по best |z|)")
        for m in meta[:6]:
            print(f"           {m['feature_id']:18} {m['target']:10} "
                  f"гипотез {m['hypotheses']:3d} | прошло {m['passed_threshold']:2d} "
                  f"| доля {m['pass_rate']} | best |z| {m['best_abs_z']}")
        out["meta"] = meta[:6]

        # --- 7. Повторный тот же батч ----------------------------------------
        ctx2 = memory.get_memory_context(s, cands, dataset_version=dsv,
                                         feature_versions=fvers, policy_hashes=pol)
        print(f"\nMEMORY CONTEXT (тот же батч повторно)")
        print(f"           кандидатов на входе {ctx2['candidates_in']} | "
              f"считать {ctx2['to_evaluate']} | пропустить {ctx2['skipped']}")
        print(f"           вердикты: {ctx2['verdicts']}")
        out["context_after"] = {k: ctx2[k] for k in
                                ("candidates_in", "to_evaluate", "skipped", "verdicts")}

        # --- 8. Прямой вопрос к памяти ----------------------------------------
        q = memory.ask_memory(s, [Condition("FORM_PPG_DIFF.v1", ">=", 0.8)], "RES_HOME")
        print(f"\nВОПРОС     «FORM_PPG_DIFF >= 0.8 -> RES_HOME: проверяли?»")
        print(f"           область {q['region']['region_key']}: "
              f"проверено {q['region']['hypotheses_tested']}, "
              f"лучший |z| {q['region']['best_abs_z']}, "
              f"прошло порог {q['region']['passed_threshold']}")
        print(f"           похожих гипотез в памяти: {q['checked_before']}")
        for r in q["results"][:3]:
            print(f"           {r['hypothesis_id']} {r['conditions'][0]['op']}"
                  f"{r['conditions'][0]['threshold']:>6} n={r['n_signals']:4d} "
                  f"z={r['z']:.2f} прошла порог={r['passed_batch_threshold']}")
        out["ask"] = q["region"]
    return out


if __name__ == "__main__":
    main()
