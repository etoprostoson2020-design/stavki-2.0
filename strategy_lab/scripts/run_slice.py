"""Первый vertical slice целиком.

    Football-Data CSV -> RAW snapshot -> Data Audit -> Canonical Fixtures
        -> Time Machine -> Feature Factory -> Leakage test -> Experiment

Повторный запуск обязан дать тот же result_hash.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select

from fsl import logging as fsl_logging
from fsl.acquisition.manager import ensure_sources, import_seasons
from fsl.audit.auditor import run_audit
from fsl.canonical.builder import build_canonical, dataset_version_for
from fsl.db import session
from fsl.experiments.engine import Condition, run_experiment
from fsl.features import catalogue  # noqa: F401  — регистрирует признаки
from fsl.features.compute import compute_features, coverage, write_parquet
from fsl.features.registry import REGISTRY
from fsl.models import Experiment, Fixture, Team
from fsl.research.holdout import guard_discovery, mark_seen, remaining, seed
from fsl.settings import get_settings
from fsl.temporal.time_machine import leakage_regression_test

LEAGUE = "ESP_1"
BLOCKS = {
    "DISCOVERY": ["16-17", "17-18", "18-19", "19-20", "20-21", "21-22"],
    "VALIDATION": ["22-23", "23-24"],
    "TEST": ["24-25", "25-26"],
}
#: Фактическое состояние на 13.09.2026: блоки discovery и validation уже
#: просмотрены в исследовании v4, test остаётся закрытым.
ALREADY_SEEN = BLOCKS["DISCOVERY"] + BLOCKS["VALIDATION"]

FEATURE_KEYS = ["FORM_PPG_DIFF.v1", "FORM_PPG_DIFF.v2", "GOALS_FOR_HOME.v1",
                "REST_DAYS_DIFF.v1"]


def load_fixtures(sess, league: str, seasons: list[str]) -> list[dict]:
    rows = sess.scalars(select(Fixture).where(
        Fixture.league == league, Fixture.season.in_(seasons))
        .order_by(Fixture.sync_batch, Fixture.id)).all()
    names = {t.id: t.canonical_name for t in sess.scalars(select(Team)).all()}
    return [{
        "fixture_id": f.id, "league": f.league, "season": f.season,
        "kickoff_utc": f.kickoff_utc, "kickoff_precision": f.kickoff_precision,
        "sync_batch": f.sync_batch,
        "home_team": names[f.home_team_id], "away_team": names[f.away_team_id],
        "fthg": f.fthg, "ftag": f.ftag, "ftr": f.ftr,
        "hthg": f.hthg, "htag": f.htag, "stats": f.stats,
    } for f in rows]


def main(league: str = LEAGUE, seasons: list[str] | None = None,
         local_dir: str = "/mnt/user-data/uploads", persist: bool = True) -> dict:
    settings = get_settings()
    fsl_logging.configure(settings.log_level)
    seasons = seasons or BLOCKS["DISCOVERY"]
    out: dict = {}

    with session() as s:
        ensure_sources(s)
        seed(s, league, BLOCKS)
        mark_seen(s, league, ALREADY_SEEN, by="research_v4",
                  note="лаборатория и валидация просмотрены на этапе v4")

        # --- 0. Holdout Ledger: батч не должен обнулять остаток --------------
        guard = guard_discovery(s, league, seasons)
        state = remaining(s, league)
        out["holdout"] = {**state, "batch": guard}
        print(f"\nHOLDOUT LEDGER  просмотрено {len(state['seen'])}/{state['total_seasons']} "
              f"| неоткрыто {state['unseen']} | батч открывает {guard['would_open'] or '—'}")

        # --- 1. RAW ----------------------------------------------------------
        local = {x: Path(local_dir) / f"{x}.csv" for x in seasons}
        local = {k: v for k, v in local.items() if v.exists()}
        snaps = import_seasons(s, league, seasons, local_files=local)
        out["raw"] = [{"season": x.season, "rows": x.n_rows, "cols": x.n_cols,
                       "sha256": x.sha256[:16]} for x in snaps]
        print(f"\nRAW  сезонов {len(snaps)} | "
              f"строк {sum(x.n_rows for x in snaps)} | "
              f"столбцов {sorted({x.n_cols for x in snaps})}")

        dsv = dataset_version_for(s, league, seasons)
        out["dataset_version"] = dsv
        print(f"     dataset_version {dsv}")

        # --- 2. CANONICAL ----------------------------------------------------
        already = s.scalar(select(Fixture).where(Fixture.league == league,
                                                 Fixture.dataset_version == dsv))
        if already is None:
            n = build_canonical(s, league, seasons, dsv)
        else:
            n = len(load_fixtures(s, league, seasons))
        fixtures = load_fixtures(s, league, seasons)
        batches = len({f["sync_batch"] for f in fixtures})
        exact = sum(1 for f in fixtures if f["kickoff_precision"] == "EXACT")
        out["canonical"] = {"fixtures": len(fixtures), "sync_batches": batches,
                            "kickoff_exact": exact,
                            "kickoff_date_only": len(fixtures) - exact}
        print(f"\nCANONICAL  матчей {len(fixtures)} | синхронных блоков {batches} | "
              f"время начала известно у {exact}, неизвестно у {len(fixtures)-exact}")

        # --- 3. AUDIT --------------------------------------------------------
        audit = run_audit(s, league, seasons, dsv)
        out["audit"] = audit
        print(f"\nAUDIT  нарушений целостности {audit['integrity_violations']} | "
              f"grade {audit['research_grade']} | конфликтов источников {audit['source_conflicts']}")
        print("       выбросы (не блокируют): " +
              ", ".join(f"{k}={v}" for k, v in audit["outliers"].items() if v) or "нет")

        # --- 4. FEATURES -----------------------------------------------------
        specs = [REGISTRY.get(k) for k in FEATURE_KEYS]
        values = compute_features(fixtures, specs)
        cov = coverage(values)
        out["features"] = cov
        print("\nFEATURES")
        for k, c in cov.items():
            print(f"       {k:22} покрытие {c['coverage']:.3f}  "
                  f"UNAVAILABLE {c['unavailable']}")
        write_parquet(values, fixtures,
                      settings.parquet_dir / f"features_{league}_{dsv}.parquet",
                      dsv, {sp.key: sp.definition_hash() for sp in specs})

        # --- 5. LEAKAGE ------------------------------------------------------
        report = leakage_regression_test(
            fixtures, lambda fx: compute_features(fx, specs), n_points=6)
        out["leakage"] = report
        print(f"\nLEAKAGE  точек {len(report['points'])} | "
              f"расхождений в прошлом {report['discrepancies']} | "
              f"{'ЧИСТО' if report['clean'] else 'ЕСТЬ УТЕЧКА'}")
        for p in report["points"]:
            print(f"       блок >= {p['batch']:4d}: испорчено {p['corrupted_fixtures']:4d} "
                  f"-> расхождений {p['discrepancies']}")
        if not report["clean"]:
            raise SystemExit("HARD STOP: обнаружена утечка будущего")

        # --- 6. EXPERIMENT ---------------------------------------------------
        exp = run_experiment(
            fixtures, values,
            conditions=[Condition("FORM_PPG_DIFF.v1", ">=", 1.0)],
            target="RES_HOME",
            hypothesis="Если разница очков за матч за 5 туров у хозяев не меньше 1.0, "
                       "то хозяева выигрывают чаще базового уровня блока",
            dataset_version=dsv,
            feature_versions={sp.key: sp.definition_hash() for sp in specs})
        out["experiment"] = exp
        print(f"\nEXPERIMENT  {exp['experiment_id']}")
        print(f"       {exp['hypothesis']}")
        print(f"       eligible {exp['n_eligible']} | сигналов {exp['n_signals']} "
              f"({exp['signal_frequency']:.3f}) | попаданий {exp['n_successes']}")
        print(f"       baseline {exp['baseline']:.4f} -> hit {exp['hit_rate']:.4f} | "
              f"uplift {exp['absolute_uplift']:+.4f} (x{exp['relative_uplift']:.2f}) | "
              f"z {exp['z']:.2f}")
        print(f"       CI95 [{exp['ci95_low']:.3f}; {exp['ci95_high']:.3f}] | "
              f"команд в сигналах {exp['per_team_concentration']['distinct_teams']} | "
              f"доля топ-5 {exp['per_team_concentration']['top5_share']}")
        for season, ps in exp["per_season"].items():
            print(f"       {season}: n={ps['n_signals']:4d} base {ps['baseline']:.3f} "
                  f"hit {ps['hit_rate']:.3f} uplift {ps['uplift']:+.3f}")
        print(f"       RESULT HASH {exp['result_hash']}")

        if persist:
            ex = s.scalar(select(Experiment).where(
                Experiment.experiment_id == exp["experiment_id"]))
            if ex is None:
                s.add(Experiment(
                    experiment_id=exp["experiment_id"], hypothesis=exp["hypothesis"],
                    league=exp["league"], seasons=exp["seasons"], target=exp["target"],
                    conditions=exp["conditions"], n_eligible=exp["n_eligible"],
                    n_signals=exp["n_signals"], n_successes=exp["n_successes"],
                    signal_frequency=exp["signal_frequency"], baseline=exp["baseline"],
                    hit_rate=exp["hit_rate"], absolute_uplift=exp["absolute_uplift"],
                    relative_uplift=exp["relative_uplift"], ci95_low=exp["ci95_low"],
                    ci95_high=exp["ci95_high"], z=exp["z"], per_season=exp["per_season"],
                    per_team_concentration=exp["per_team_concentration"],
                    dataset_version=dsv, feature_versions=exp["feature_versions"],
                    environment_lock=exp["environment_lock"],
                    policy_version=exp["policy_version"],
                    result_hash=exp["result_hash"]))
                print("       записан в реестр экспериментов")
            else:
                print("       уже в реестре — тот же result_hash, повторной записи нет")
    return out


def slice_features(league: str, seasons: list[str]) -> dict:
    with session() as s:
        fixtures = load_fixtures(s, league, seasons)
    specs = [REGISTRY.get(k) for k in FEATURE_KEYS]
    return coverage(compute_features(fixtures, specs))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default=LEAGUE)
    ap.add_argument("--seasons", nargs="*", default=None)
    ap.add_argument("--local-dir", default=os.environ.get("FSL_LOCAL_CSV_DIR",
                                                          "/mnt/user-data/uploads"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = main(a.league, a.seasons, a.local_dir)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
