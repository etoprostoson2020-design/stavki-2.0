"""Семейства стратегий по пересечению сигналов.

Документ 06: коррелированные стратегии не считаются независимыми открытиями.
Две стратегии, отбирающие в основном одни и те же матчи, — один механизм,
а не два, и учитываться в отчёте должны как один.
"""
from __future__ import annotations

from sqlalchemy import select

from fsl.hashing import stable_hash
from fsl.memory.fingerprints import jaccard
from fsl.models import StrategyFamily, StrategySignalSet

FAMILY_JACCARD = 0.50


def store_signals(sess, strategy_id: str, version: int, dataset_version: str,
                  fixture_ids: list[int]) -> StrategySignalSet:
    from fsl.memory.fingerprints import signal_fingerprint
    row = sess.scalar(select(StrategySignalSet).where(
        StrategySignalSet.strategy_id == strategy_id,
        StrategySignalSet.version == version,
        StrategySignalSet.dataset_version == dataset_version))
    if row is not None:
        return row
    row = StrategySignalSet(strategy_id=strategy_id, version=version,
                            dataset_version=dataset_version,
                            fixture_ids=sorted(int(x) for x in fixture_ids),
                            signal_fingerprint=signal_fingerprint(fixture_ids))
    sess.add(row)
    sess.flush()
    return row


def similarity_matrix(sess) -> dict:
    rows = sess.scalars(select(StrategySignalSet)).all()
    keys = [f"{r.strategy_id}.v{r.version}" for r in rows]
    sets = [set(r.fixture_ids) for r in rows]
    return {"members": keys,
            "jaccard": [[round(jaccard(a, b), 3) for b in sets] for a in sets]}


def rebuild_families(sess, threshold: float = FAMILY_JACCARD) -> list[dict]:
    """Кластеризация связностью: рёбра там, где пересечение выше порога."""
    rows = sess.scalars(select(StrategySignalSet)).all()
    keys = [f"{r.strategy_id}.v{r.version}" for r in rows]
    sets = [set(r.fixture_ids) for r in rows]

    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    max_j = 0.0
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            v = jaccard(sets[i], sets[j])
            max_j = max(max_j, v)
            if v >= threshold:
                parent[find(i)] = find(j)

    clusters: dict[int, list[str]] = {}
    for i, k in enumerate(keys):
        clusters.setdefault(find(i), []).append(k)

    sess.query(StrategyFamily).delete()
    out = []
    for members in clusters.values():
        fid = "FAM-" + stable_hash(sorted(members))[:10]
        inner = 0.0
        idxs = [keys.index(m) for m in members]
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                inner = max(inner, jaccard(sets[idxs[a]], sets[idxs[b]]))
        sess.add(StrategyFamily(family_id=fid, label=" + ".join(sorted(members)[:3]),
                                members=sorted(members),
                                max_pairwise_jaccard=round(inner, 3)))
        out.append({"family_id": fid, "members": sorted(members),
                    "max_pairwise_jaccard": round(inner, 3)})
    sess.flush()
    return out
