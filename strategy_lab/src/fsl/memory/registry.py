"""Experiment Registry: что проверялось и чем кончилось.

Ключевой принцип документа 06: каждый новый батч начинается с обращения
к памяти. Лаборатория обязана накапливать знание, а не искать заново одно
и то же.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from fsl.hashing import stable_hash
from fsl.logging import get_logger
from fsl.memory.fingerprints import (exact_fingerprint, region_key,
                                     semantic_fingerprint, signal_fingerprint)
from fsl.models import HypothesisRecord, MetaFeatureStat

log = get_logger(__name__)


def record_hypothesis(sess, *, league: str, seasons: list[str], conditions, target: str,
                      feature_versions: dict, dataset_version: str,
                      policy_hashes: dict, result: dict | None = None,
                      signal_fixture_ids: list[int] | None = None,
                      batch_id: str | None = None, origin: str = "RULE_GENERATOR",
                      passed_threshold: bool | None = None) -> tuple[HypothesisRecord, bool]:
    """Записывает гипотезу. Возвращает (запись, была_ли_новой).

    Повторная встреча того же exact-отпечатка не создаёт вторую строку:
    инкрементируется счётчик встреч. Это и есть защита от «потока дубликатов».
    """
    ef = exact_fingerprint(conditions, target, dataset_version, feature_versions,
                           policy_hashes)
    existing = sess.scalar(select(HypothesisRecord).where(
        HypothesisRecord.exact_fingerprint == ef))
    if existing is not None:
        existing.times_seen += 1
        existing.last_seen_at = dt.datetime.now(dt.timezone.utc)
        sess.flush()
        return existing, False

    rec = HypothesisRecord(
        hypothesis_id="HYP-" + ef[:12],
        league=league, seasons=sorted(seasons), target=target,
        conditions=[c.as_dict() if hasattr(c, "as_dict") else dict(c) for c in conditions],
        feature_versions=dict(feature_versions),
        exact_fingerprint=ef,
        semantic_fingerprint=semantic_fingerprint(conditions, target),
        signal_fingerprint=(signal_fingerprint(signal_fixture_ids)
                            if signal_fixture_ids else None),
        region_key=region_key(conditions, target),
        origin=origin, batch_id=batch_id, dataset_version=dataset_version,
        n_signals=(result or {}).get("n_signals"),
        baseline=(result or {}).get("baseline"),
        hit_rate=(result or {}).get("hit_rate"),
        absolute_uplift=(result or {}).get("absolute_uplift"),
        z=(result or {}).get("z"),
        passed_batch_threshold=passed_threshold,
        status="EVALUATED" if result else "PROPOSED")
    sess.add(rec)
    sess.flush()
    return rec, True


def find_exact(sess, conditions, target, dataset_version, feature_versions,
               policy_hashes) -> HypothesisRecord | None:
    ef = exact_fingerprint(conditions, target, dataset_version, feature_versions,
                           policy_hashes)
    return sess.scalar(select(HypothesisRecord).where(
        HypothesisRecord.exact_fingerprint == ef))


def find_similar(sess, conditions, target, *, limit: int = 20) -> list[HypothesisRecord]:
    """«Такая логика уже проверялась?» — по семантическому отпечатку."""
    sf = semantic_fingerprint(conditions, target)
    return list(sess.scalars(select(HypothesisRecord)
                             .where(HypothesisRecord.semantic_fingerprint == sf)
                             .order_by(HypothesisRecord.z.desc().nullslast())
                             .limit(limit)).all())


def find_by_signal(sess, fixture_ids: list[int]) -> list[HypothesisRecord]:
    """Другая формула, то же множество матчей — не два открытия, а одно."""
    return list(sess.scalars(select(HypothesisRecord).where(
        HypothesisRecord.signal_fingerprint == signal_fingerprint(fixture_ids))).all())


def region_history(sess, conditions, target) -> dict:
    """Что известно про этот участок пространства поиска."""
    rk = region_key(conditions, target)
    rows = list(sess.scalars(select(HypothesisRecord)
                             .where(HypothesisRecord.region_key == rk)).all())
    zs = [abs(r.z) for r in rows if r.z is not None]
    return {"region_key": rk, "hypotheses_tested": len(rows),
            "best_abs_z": round(max(zs), 2) if zs else None,
            "passed_threshold": sum(1 for r in rows if r.passed_batch_threshold),
            "promoted_to_strategy": sum(1 for r in rows if r.strategy_id)}


def update_meta(sess, conditions, target, *, z: float | None,
                passed: bool | None, outcome: str | None = None) -> None:
    """Meta Memory: накопленная статистика признака по таргету."""
    for c in conditions:
        d = c.as_dict() if hasattr(c, "as_dict") else dict(c)
        fid = d["feature"].split(".")[0]
        row = sess.scalar(select(MetaFeatureStat).where(
            MetaFeatureStat.feature_id == fid, MetaFeatureStat.target == target))
        if row is None:
            row = MetaFeatureStat(feature_id=fid, target=target)
            sess.add(row)
            sess.flush()
        row.hypotheses += 1
        if passed:
            row.passed_threshold += 1
        if z is not None:
            row.best_abs_z = max(row.best_abs_z, abs(z))
        if outcome == "ROBUST":
            row.robust += 1
        elif outcome == "CANDIDATE":
            row.candidates += 1
        elif outcome == "KILL":
            row.killed += 1
        elif outcome == "PARK":
            row.parked += 1
        row.updated_at = dt.datetime.now(dt.timezone.utc)
    sess.flush()


def meta_summary(sess) -> list[dict]:
    rows = sess.scalars(select(MetaFeatureStat)
                        .order_by(MetaFeatureStat.best_abs_z.desc())).all()
    return [{"feature_id": r.feature_id, "target": r.target, "hypotheses": r.hypotheses,
             "passed_threshold": r.passed_threshold, "candidates": r.candidates,
             "robust": r.robust, "killed": r.killed, "parked": r.parked,
             "best_abs_z": round(r.best_abs_z, 2),
             "pass_rate": round(r.passed_threshold / r.hypotheses, 3) if r.hypotheses else None}
            for r in rows]


def registry_stats(sess) -> dict:
    total = sess.scalar(select(func.count()).select_from(HypothesisRecord)) or 0
    dupes = sess.scalar(select(func.coalesce(func.sum(HypothesisRecord.times_seen - 1), 0)))
    return {"hypotheses": total, "duplicate_encounters": int(dupes or 0),
            "with_signals": sess.scalar(select(func.count()).select_from(HypothesisRecord)
                                        .where(HypothesisRecord.signal_fingerprint.isnot(None))) or 0,
            "promoted": sess.scalar(select(func.count()).select_from(HypothesisRecord)
                                    .where(HypothesisRecord.strategy_id.isnot(None))) or 0,
            "registry_hash": stable_hash({"n": total})}
