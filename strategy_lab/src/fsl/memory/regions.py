"""Исчерпанные области поиска.

Ретест разрешён только при реальном изменении данных, признака, версии,
сезона или метода. Иначе генератор будет ходить по одному и тому же кругу.
"""
from __future__ import annotations

from sqlalchemy import select

from fsl.logging import get_logger
from fsl.models import ExhaustedRegion, HypothesisRecord

log = get_logger(__name__)

MIN_TESTED_TO_EXHAUST = 10


def mark_exhausted_regions(sess, league: str, dataset_version: str,
                           batch_threshold: float,
                           min_tested: int = MIN_TESTED_TO_EXHAUST) -> list[dict]:
    """Область исчерпана, если в ней много проверено и ничего не прошло порог."""
    rows = sess.scalars(select(HypothesisRecord).where(
        HypothesisRecord.league == league,
        HypothesisRecord.dataset_version == dataset_version)).all()
    by_region: dict[str, list[HypothesisRecord]] = {}
    for r in rows:
        by_region.setdefault(r.region_key, []).append(r)

    marked = []
    for rk, group in by_region.items():
        if len(group) < min_tested:
            continue
        zs = [abs(g.z) for g in group if g.z is not None]
        best = max(zs) if zs else 0.0
        if best >= batch_threshold:
            continue                      # что-то прошло — область не исчерпана
        existing = sess.scalar(select(ExhaustedRegion).where(
            ExhaustedRegion.region_key == rk,
            ExhaustedRegion.dataset_version == dataset_version))
        if existing is not None:
            continue
        sess.add(ExhaustedRegion(
            region_key=rk, league=league, dataset_version=dataset_version,
            hypotheses_tested=len(group), best_abs_z=round(best, 2),
            batch_threshold=batch_threshold,
            reason=f"проверено {len(group)} гипотез, лучший |z| {best:.2f} "
                   f"ниже порога батча {batch_threshold}"))
        marked.append({"region_key": rk, "tested": len(group),
                       "best_abs_z": round(best, 2)})
    sess.flush()
    if marked:
        log.info("memory.regions_exhausted", count=len(marked))
    return marked


def is_exhausted(sess, region: str, dataset_version: str) -> ExhaustedRegion | None:
    """Исчерпана ли область НА ЭТИХ данных. На новых — вопрос открыт заново."""
    return sess.scalar(select(ExhaustedRegion).where(
        ExhaustedRegion.region_key == region,
        ExhaustedRegion.dataset_version == dataset_version))


def list_exhausted(sess) -> list[dict]:
    rows = sess.scalars(select(ExhaustedRegion)
                        .order_by(ExhaustedRegion.created_at.desc())).all()
    return [{"region_key": r.region_key, "dataset_version": r.dataset_version,
             "tested": r.hypotheses_tested, "best_abs_z": r.best_abs_z,
             "threshold": r.batch_threshold, "reason": r.reason} for r in rows]
