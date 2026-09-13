"""Фаза 6. Validation Engine на реальных данных Ла Лиги.

Показывает четыре вещи:
  1. порог значимости считается для каждого батча и зависит от его размера;
  2. негативные контроли порог не проходят;
  3. критерий заморожен вместе с формулой и его подмена ловится;
  4. просмотренный блок не может выдать ROBUST, каким бы сильным ни был z.
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
from sqlalchemy import select

from fsl import logging as fsl_logging
from fsl.acquisition.manager import import_seasons
from fsl.canonical.builder import build_canonical, dataset_version_for
from fsl.db import session
from fsl.experiments.engine import Condition, run_experiment
from fsl.features import catalogue  # noqa: F401
from fsl.features.compute import compute_features
from fsl.features.registry import REGISTRY
from fsl.hashing import stable_hash
from fsl.models import Fixture, SearchBatchRecord, Strategy, ValidationRun
from fsl.memory import api as memory
from fsl.research.holdout import remaining
from fsl.validation.engine import (HardFail, evaluate_oos, freeze_strategy,
                                   qualification_gate, run_robustness,
                                   structural_mechanism_gate)
from fsl.validation.null_world import make_negative_controls, run_null_world
from fsl.validation.policy import qualification_policy, statistical_policy
from fsl.validation.search_batch import (Candidate, batch_fingerprint, build_matrices,
                                         z_scores)
from scripts.run_slice import BLOCKS, FEATURE_KEYS, LEAGUE, load_fixtures

TARGET_SET = ["RES_HOME", "RES_AWAY", "OVER_25", "BTTS_YES", "FH_GOAL"]
QUANTILES = [0.10, 0.25, 0.40, 0.60, 0.75, 0.90]


def ensure_block(s, league, seasons, local_dir="/mnt/user-data/uploads"):
    from pathlib import Path
    have = s.scalar(select(Fixture).where(Fixture.league == league,
                                          Fixture.season.in_(seasons)))
    if have is None:
        local = {x: Path(local_dir) / f"{x}.csv" for x in seasons}
        import_seasons(s, league, seasons, local_files={k: v for k, v in local.items()
                                                        if v.exists()})
        build_canonical(s, league, seasons, dataset_version_for(s, league, seasons))
    return load_fixtures(s, league, seasons)


def build_batch(values, keys, targets, quantiles) -> list[Candidate]:
    """Сетка порогов по квантилям признака. Грубая, как требует документ 04."""
    out = []
    for key in keys:
        col = np.array([v[key] for v in values.values() if v[key] is not None], dtype=float)
        if col.size < 100:
            continue
        for q in quantiles:
            thr = float(np.round(np.quantile(col, q), 3))
            op = "<=" if q < 0.5 else ">="
            for t in targets:
                out.append(Candidate(
                    candidate_id=f"{key}|{op}|{thr}|{t}",
                    conditions=(Condition(key, op, thr),), target=t,
                    family=key.split(".")[0], kind="REAL"))
    return out


def main() -> dict:
    fsl_logging.configure("WARNING")
    qual, stat = qualification_policy(), statistical_policy()
    report: dict = {}

    with session() as s:
        disc_seasons = BLOCKS["DISCOVERY"]
        val_seasons = BLOCKS["VALIDATION"]
        ledger = remaining(s, LEAGUE)
        dsv = dataset_version_for(s, LEAGUE, disc_seasons)

        disc = load_fixtures(s, LEAGUE, disc_seasons)
        specs = [REGISTRY.get(k) for k in FEATURE_KEYS]
        disc_values = compute_features(disc, specs)
        fvers = {sp.key: sp.definition_hash() for sp in specs}

        print(f"\nПОЛИТИКИ   QUALIFICATION {qual.version} hash {qual.hash}")
        print(f"           STATISTICAL   {stat.version} hash {stat.hash}")
        print(f"HOLDOUT    просмотрено {len(ledger['seen'])}/{ledger['total_seasons']}, "
              f"неоткрыто {ledger['unseen']}")

        # --- 1. Батч и негативные контроли ----------------------------------
        cands = build_batch(disc_values, FEATURE_KEYS, TARGET_SET, QUANTILES)
        neg_arrays = make_negative_controls(
            disc_values, [f["fixture_id"] for f in disc],
            n_permuted=stat.get("negative_controls", "permuted_features", default=25),
            n_noise=stat.get("negative_controls", "noise_features", default=15))
        neg_cands = [Candidate(candidate_id=name, conditions=(), target="RES_HOME",
                               family="NEGATIVE",
                               kind="NEG_NOISE" if "noise" in name else "NEG_PERMUTED")
                     for name in neg_arrays]
        all_cands = cands + neg_cands
        # Документ 06: батч начинается с обращения к памяти, а не с расчёта.
        mem = memory.get_memory_context(
            s, cands, dataset_version=dsv, feature_versions=fvers,
            policy_hashes={"qualification": qual.hash, "statistical": stat.hash})
        print(f"\nMEMORY     в реестре гипотез {mem['registry']['hypotheses']} | "
              f"из {mem['candidates_in']} кандидатов считать {mem['to_evaluate']}, "
              f"пропустить {mem['skipped']}")
        if mem["verdicts"]:
            print(f"           вердикты памяти: {mem['verdicts']}")

        bm = build_matrices(disc, disc_values, all_cands, negative_controls=neg_arrays)
        print(f"\nBATCH      реальных кандидатов {len(cands)} | "
              f"негативных контролей {len(neg_cands)} | всего {len(all_cands)}")

        # --- 2. Null-world и порог батча ------------------------------------
        nw = run_null_world(bm, worlds=stat.get("null_world", "worlds", default=300),
                            method=stat.get("null_world", "primary_method"),
                            percentile=stat.get("null_world", "fwer_percentile", default=95),
                            seed=stat.get("null_world", "seed", default=2024))
        print(f"NULL WORLD {nw.method}, миров {nw.worlds}")
        print(f"           порог FWER |z| = {nw.fwer_threshold} "
              f"(медиана max|z| {nw.median_max_z})")
        print(f"           реальных выше порога {nw.n_real_passing} из {len(cands)} | "
              f"max|z| реальный {nw.max_abs_z_real}")
        print(f"           НЕГАТИВНЫХ ВЫШЕ ПОРОГА {nw.n_negative_passing} из "
              f"{nw.n_negative_controls} | их max|z| {nw.max_abs_z_negative}")
        report["memory"] = {k: mem[k] for k in
                            ("candidates_in", "to_evaluate", "skipped", "verdicts")}
        report["null_world"] = nw.as_dict()

        # --- 3. Порог как функция размера батча ------------------------------
        print("\nПОРОГ ЗАВИСИТ ОТ РАЗМЕРА БАТЧА (тот же датасет, подвыборки кандидатов)")
        rng = np.random.default_rng(0)
        scaling = []
        real_idx = np.array([i for i, c in enumerate(all_cands) if c.kind == "REAL"])
        for k in (10, 30, 60, 120, len(real_idx)):
            sub = np.sort(rng.choice(real_idx, min(k, len(real_idx)), replace=False))
            sub_bm = build_matrices(disc, disc_values, [all_cands[i] for i in sub],
                                    negative_controls=neg_arrays)
            r = run_null_world(sub_bm, worlds=150,
                               method=stat.get("null_world", "primary_method"), seed=2024)
            scaling.append({"candidates": int(len(sub)), "threshold": r.fwer_threshold})
            print(f"           кандидатов {len(sub):4d} -> порог |z| {r.fwer_threshold}")
        report["threshold_scaling"] = scaling

        # --- 4. Лучший кандидат: gate + робастность --------------------------
        z_real = z_scores(bm)
        order = [i for i in np.argsort(-np.abs(np.nan_to_num(z_real)))
                 if all_cands[i].kind == "REAL"]
        best = all_cands[order[0]]
        cond = list(best.conditions)
        print(f"\nЛУЧШИЙ КАНДИДАТ  {best.candidate_id}  |z| {abs(z_real[order[0]]):.2f}")

        discovery = run_experiment(disc, disc_values, cond, best.target,
                                   hypothesis=f"discovery {best.candidate_id}",
                                   dataset_version=dsv, feature_versions=fvers)
        robust = run_robustness(disc, disc_values, cond, best.target,
                                window_alternatives={"окно 10": "FORM_PPG_DIFF.v2"}
                                if cond[0].feature_key == "FORM_PPG_DIFF.v1" else None)
        gate = qualification_gate(discovery, robust, qual)
        print(f"QUALIFICATION GATE  {'ПРОЙДЕН' if gate['passed'] else 'НЕ ПРОЙДЕН'}")
        for k, v in gate["checks"].items():
            print(f"           {k:26} {v['value']} против {v['required']}  "
                  f"{'ок' if v['ok'] else 'НЕТ'}")
        print(f"ROBUSTNESS walk-forward uplift {robust['walk_forward']['uplift']} "
              f"(n={robust['walk_forward']['n']})")
        loto = robust["leave_one_team_out"]
        print(f"           LOTO команд {loto['evaluated_teams']}, uplift "
              f"[{loto['min_uplift']}; {loto['max_uplift']}], знак стабилен "
              f"{loto['sign_stable']}")
        pn = robust["parameter_neighborhood"]
        print(f"           соседство порога: знак стабилен {pn['sign_stable']}, "
              f"разброс uplift {pn['spread']}")
        print(f"           концентрация: команд {robust['team_concentration']['distinct_teams']}, "
              f"топ-5 {robust['team_concentration']['top5_share']}")
        tc = robust["temporal_clustering"]
        print(f"           кластеризация: индекс дисперсии {tc['dispersion_index']} "
              f"(1.0 — равномерный поток)")
        mb = robust["missingness_bias"]
        print(f"           смещение пригодности: eligible {mb['eligible_rate']} против "
              f"ineligible {mb['ineligible_rate']}, z {mb['z']}")
        report["gate"] = gate
        report["robustness"] = robust

        # --- 5. Заморозка ----------------------------------------------------
        fz = freeze_strategy("STR-000001", 1, cond, best.target, fvers, dsv,
                             seen_seasons=ledger["seen"], qualification=qual,
                             statistical=stat)
        print(f"\nFREEZE     strategy_hash {fz.strategy_hash} | formula {fz.formula_hash}")
        print(f"           критерий заморожен вместе с формулой: {fz.qualification_policy_hash}")

        # --- 6. OOS на блоке валидации (он уже просмотрен) -------------------
        val = ensure_block(s, LEAGUE, val_seasons)
        val_values = compute_features(val, specs)
        res = evaluate_oos(fz, discovery, val, val_values, oos_seasons=val_seasons,
                           unseen_at_freeze=ledger["unseen"], qualification=qual,
                           statistical=stat, null_result=nw)
        o = res["oos"]
        print(f"\nOOS        сезоны {res['oos_seasons']} | валидность {res['oos_validity']}")
        print(f"           n {o['n_signals']} | baseline {o['baseline']:.4f} -> "
              f"hit {o['hit_rate']:.4f} | uplift {o['absolute_uplift']:+.4f} | z {o['z']:.2f}")
        print(f"           критерий: " + ", ".join(
            f"{k}={'да' if v else 'НЕТ'}" for k, v in res["criterion"].items()))
        print(f"           ВЕРДИКТ {res['outcome']} -> {res['action']} | "
              f"класс {res['strategy_class']}")
        for n in res["notes"]:
            print(f"           ! {n}")
        report["oos"] = res

        # --- 7. Подмена критерия после просмотра OOS -------------------------
        tampered = qual.__class__(name=qual.name, version=qual.version,
                                  payload={**qual.payload,
                                           "oos_pass": {**qual.payload["oos_pass"],
                                                        "min_z": 0.5}})
        try:
            evaluate_oos(fz, discovery, val, val_values, oos_seasons=val_seasons,
                         unseen_at_freeze=ledger["unseen"], qualification=tampered,
                         statistical=stat, null_result=nw)
            print("\nTAMPER     ОШИБКА: подмена критерия не обнаружена")
            report["tamper_detected"] = False
        except HardFail as e:
            print(f"\nTAMPER     подмена критерия поймана: {e.code}")
            report["tamper_detected"] = True

        # --- 8. Structural Mechanism -----------------------------------------
        sm = structural_mechanism_gate([])
        print(f"STRUCTURAL {sm['eligible']} — {sm['reason']}")
        report["structural"] = sm

        # --- 9. Запись -------------------------------------------------------
        bid = "BATCH-" + batch_fingerprint(all_cands)[:10]
        if s.scalar(select(SearchBatchRecord).where(SearchBatchRecord.batch_id == bid)) is None:
            s.add(SearchBatchRecord(
                batch_id=bid, research_question="форма и отдых против исходов матча",
                league=LEAGUE, seasons=disc_seasons, n_candidates=len(cands),
                n_negative_controls=len(neg_cands), dataset_version=dsv,
                statistical_policy_hash=stat.hash, null_world=nw.as_dict(),
                fwer_threshold=nw.fwer_threshold, n_passing=nw.n_real_passing,
                fingerprint=batch_fingerprint(all_cands)))
        existing = s.scalar(select(Strategy).where(
            Strategy.strategy_hash == fz.strategy_hash))
        if existing is not None:
            # Формула и заморозка неизменны, но стадия отражает ПОСЛЕДНИЙ прогон.
            # Неизменяемая история живёт в ValidationRun, а не здесь.
            existing.strategy_class = res["strategy_class"]
            existing.action = res["action"]
            existing.park_kill_reason = "; ".join(res["notes"]) or None
        else:
            s.add(Strategy(
                strategy_id=fz.strategy_id, version=fz.version,
                name=best.candidate_id, league=LEAGUE, target=fz.target,
                conditions=[c.as_dict() for c in fz.conditions], feature_versions=fvers,
                formula_hash=fz.formula_hash, strategy_hash=fz.strategy_hash,
                qualification_policy_hash=fz.qualification_policy_hash,
                statistical_policy_hash=fz.statistical_policy_hash,
                seen_seasons=list(fz.seen_seasons),
                frozen_at=dt.datetime.fromisoformat(fz.frozen_at),
                stage="VALIDATING", strategy_class=res["strategy_class"],
                action=res["action"],
                park_kill_reason="; ".join(res["notes"]) or None))
        rh = stable_hash(res)
        if s.scalar(select(ValidationRun).where(ValidationRun.run_hash == rh)) is None:
            s.add(ValidationRun(
                run_id="VAL-" + rh[:12], strategy_id=fz.strategy_id, version=fz.version,
                strategy_hash=fz.strategy_hash, batch_id=bid,
                engine_version=res["engine_version"],
                oos_seasons=res["oos_seasons"], oos_validity=res["oos_validity"],
                outcome=res["outcome"], action=res["action"],
                strategy_class=res["strategy_class"],
                fwer_threshold=res["fwer_threshold"], criterion=res["criterion"],
                discovery=res["discovery"], oos=res["oos"], robustness=robust,
                notes=res["notes"], run_hash=rh))
            print(f"\nЗАПИСАНО   батч {bid} | прогон VAL-{rh[:12]}")
        else:
            print(f"\nЗАПИСАНО   прогон уже есть, run_hash {rh} — повтора нет")
    return report


if __name__ == "__main__":
    r = main()
    print("\n" + json.dumps({"threshold_scaling": r["threshold_scaling"],
                             "outcome": r["oos"]["outcome"],
                             "class": r["oos"]["strategy_class"],
                             "tamper_detected": r["tamper_detected"]},
                            ensure_ascii=False))
