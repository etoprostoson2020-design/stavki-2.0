"""Search Batch: набор кандидатов, проверяемых вместе.

Батч — единица учёта множественного тестирования. Порог значимости
принадлежит батчу, а не проекту: он зависит от того, сколько гипотез
проверялось и насколько они скоррелированы между собой.

Генератор гипотез — фаза 8. Здесь батч приходит извне; Validation Engine
его не придумывает, а только оценивает.
"""
from __future__ import annotations

import dataclasses as dc

import numpy as np

from fsl.experiments.engine import TARGETS, Condition
from fsl.hashing import stable_hash


@dc.dataclass(frozen=True)
class Candidate:
    candidate_id: str
    conditions: tuple[Condition, ...]
    target: str
    family: str = "UNSPECIFIED"
    kind: str = "REAL"          # REAL | NEG_PERMUTED | NEG_NOISE

    def as_dict(self) -> dict:
        return {"candidate_id": self.candidate_id, "family": self.family,
                "kind": self.kind, "target": self.target,
                "conditions": [c.as_dict() for c in self.conditions]}

    @property
    def fingerprint(self) -> str:
        return stable_hash(self.as_dict())


@dc.dataclass
class BatchMatrices:
    """Матрицы сигналов и пригодности: (кандидаты x матчи)."""
    signal: np.ndarray
    eligible: np.ndarray
    targets: np.ndarray          # (таргеты x матчи), 0/1, nan где исход неизвестен
    target_index: dict[str, int]
    candidate_target: np.ndarray  # индекс таргета каждого кандидата
    season_of_fixture: np.ndarray
    fixture_ids: list[int]
    candidates: list[Candidate]


def build_matrices(fixtures: list[dict],
                   feature_values: dict[int, dict[str, float | None]],
                   candidates: list[Candidate],
                   *, negative_controls: dict[str, np.ndarray] | None = None
                   ) -> BatchMatrices:
    fids = [f["fixture_id"] for f in fixtures]
    pos = {fid: i for i, fid in enumerate(fids)}
    n_fix = len(fids)

    used_targets = sorted({c.target for c in candidates})
    tmat = np.full((len(used_targets), n_fix), np.nan, dtype=np.float32)
    tindex = {t: i for i, t in enumerate(used_targets)}
    for f in fixtures:
        i = pos[f["fixture_id"]]
        for t in used_targets:
            y = TARGETS[t](f)
            if y is not None:
                tmat[tindex[t], i] = float(y)

    sig = np.zeros((len(candidates), n_fix), dtype=np.float32)
    elig = np.zeros((len(candidates), n_fix), dtype=np.float32)
    ctarget = np.zeros(len(candidates), dtype=np.int64)

    for ci, cand in enumerate(candidates):
        ctarget[ci] = tindex[cand.target]
        override = (negative_controls or {}).get(cand.candidate_id)
        for f in fixtures:
            i = pos[f["fixture_id"]]
            if np.isnan(tmat[tindex[cand.target], i]):
                continue                                   # исход неизвестен
            if override is not None:
                v = override[i]
                if np.isnan(v):
                    continue
                ok = True
                fires = bool(v >= 0.0)                     # порог контролей — медиана шума
            else:
                vals = feature_values.get(f["fixture_id"], {})
                verdicts = [c.holds(vals.get(c.feature_key)) for c in cand.conditions]
                if any(v is None for v in verdicts):
                    continue                               # NOT_ELIGIBLE
                ok, fires = True, all(verdicts)
            if ok:
                elig[ci, i] = 1.0
                if fires:
                    sig[ci, i] = 1.0

    seasons = np.array([f["season"] for f in fixtures])
    return BatchMatrices(signal=sig, eligible=elig, targets=tmat, target_index=tindex,
                         candidate_target=ctarget, season_of_fixture=seasons,
                         fixture_ids=fids, candidates=candidates)


def z_scores(bm: BatchMatrices, targets: np.ndarray | None = None) -> np.ndarray:
    """z каждого кандидата против базлайна собственного eligible-множества."""
    tmat = bm.targets if targets is None else targets
    y = np.nan_to_num(tmat, nan=0.0)
    have = (~np.isnan(tmat)).astype(np.float32)

    yc = y[bm.candidate_target]                 # (кандидаты x матчи)
    hc = have[bm.candidate_target]

    ns = (bm.signal * hc).sum(1)
    ks = (bm.signal * yc).sum(1)
    ne = (bm.eligible * hc).sum(1)
    ke = (bm.eligible * yc).sum(1)

    with np.errstate(divide="ignore", invalid="ignore"):
        base = ke / ne
        cond = ks / ns
        z = (cond - base) / np.sqrt(np.maximum(base * (1 - base), 1e-12) / ns)
    z[ns < 1] = np.nan
    return z


def batch_fingerprint(candidates: list[Candidate]) -> str:
    return stable_hash(sorted(c.fingerprint for c in candidates))
