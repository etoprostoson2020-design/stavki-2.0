"""Data Audit. Coverage, missingness, целостность, конфликты источников."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from fsl.canonical.builder import CORE_FIELDS, STAT_FIELDS
from fsl.hashing import stable_hash
from fsl.logging import get_logger
from fsl.models import DataAuditReport, Fixture, RawSnapshot

log = get_logger(__name__)

#: Проверки целостности. Нарушение любой блокирует продвижение независимо от
#: того, насколько красивы найденные закономерности (документ 05, Hard Fails).
INTEGRITY_CHECKS = {
    "FTHG>=HTHG": lambda d: d.fthg < d.hthg,
    "FTAG>=HTAG": lambda d: d.ftag < d.htag,
    "HS>=HST": lambda d: d.HS < d.HST,
    "AS>=AST": lambda d: d.AS < d.AST,
    "FTR_consistent": lambda d: d.ftr != d.ftr_expected,
    "HTR_consistent": lambda d: d.htr != d.htr_expected,
    "duplicate_fixture": lambda d: d.duplicated(subset=["season", "home", "away"]),
    "self_match": lambda d: d.home == d.away,
    "negative_stat": lambda d: d[STAT_FIELDS].lt(0).any(axis=1),
}

#: Эвристики выбросов. НЕ блокируют: это повод посмотреть глазами, а не отказ.
OUTLIER_CHECKS = {
    "goals>9": lambda d: (d.fthg + d.ftag) > 9,
    "shots>40": lambda d: (d.HS > 40) | (d.AS > 40),
    "corners>20": lambda d: (d.HC > 20) | (d.AC > 20),
    "red>2": lambda d: (d.HR > 2) | (d.AR > 2),
}


def _frame(sess, league: str, seasons: list[str]) -> pd.DataFrame:
    rows = sess.scalars(select(Fixture).where(
        Fixture.league == league, Fixture.season.in_(seasons))).all()
    recs = []
    for f in rows:
        r = {"season": f.season, "home": f.home_team_id, "away": f.away_team_id,
             "fthg": f.fthg, "ftag": f.ftag, "ftr": f.ftr,
             "hthg": f.hthg, "htag": f.htag, "htr": f.htr,
             "kickoff_precision": f.kickoff_precision}
        r.update({k: f.stats.get(k) for k in STAT_FIELDS})
        recs.append(r)
    d = pd.DataFrame(recs)
    if d.empty:
        return d
    import numpy as np
    d["ftr_expected"] = np.where(d.fthg > d.ftag, "H", np.where(d.fthg < d.ftag, "A", "D"))
    d["htr_expected"] = np.where(d.hthg > d.htag, "H", np.where(d.hthg < d.htag, "A", "D"))
    return d


def run_audit(sess, league: str, seasons: list[str], dataset_version: str) -> dict:
    d = _frame(sess, league, seasons)
    if d.empty:
        raise RuntimeError("нет канонических матчей для аудита")

    integrity, total_violations = {}, 0
    for name, fn in INTEGRITY_CHECKS.items():
        n = int(pd.Series(fn(d)).fillna(False).sum())
        integrity[name] = n
        total_violations += n

    outliers = {name: int(pd.Series(fn(d)).fillna(False).sum())
                for name, fn in OUTLIER_CHECKS.items()}

    per_season = {}
    for s, sub in d.groupby("season"):
        teams = pd.concat([sub.home, sub.away]).value_counts()
        ok_structure = bool(len(teams) == 20 and (teams == 38).all()
                            and (sub.home.value_counts() == 19).all())
        per_season[s] = {
            "fixtures": int(len(sub)), "teams": int(len(teams)),
            "structure_38_19_ok": ok_structure,
            "kickoff_exact": int((sub.kickoff_precision == "EXACT").sum()),
            "kickoff_date_only": int((sub.kickoff_precision == "DATE_ONLY").sum()),
        }
        if not ok_structure:
            total_violations += 1

    missing = {c: int(d[c].isna().sum()) for c in STAT_FIELDS + ["fthg", "ftag", "hthg", "htag"]}
    coverage = {c: round(1 - v / len(d), 4) for c, v in missing.items()}

    conflicts = sess.query(  # с одним источником конфликтов нет по построению
        __import__("fsl.models", fromlist=["SourceConflict"]).SourceConflict).count()

    payload = {
        "league": league, "seasons": sorted(seasons), "fixtures": int(len(d)),
        "core_fields": CORE_FIELDS,
        "integrity": integrity, "integrity_violations": total_violations,
        "outliers": outliers, "per_season": per_season,
        "missing": missing, "coverage": coverage,
        "source_conflicts": conflicts,
        "sources": ["FOOTBALL_DATA"],
        "research_grade": "A" if total_violations == 0 else "D",
    }
    payload["report_hash"] = stable_hash(payload)

    sess.add(DataAuditReport(league=league, dataset_version=dataset_version,
                             n_violations=total_violations, payload=payload,
                             report_hash=payload["report_hash"]))
    sess.flush()
    log.info("audit.done", fixtures=len(d), violations=total_violations,
             grade=payload["research_grade"])
    return payload
